<?php
/**
 * Бэкенд для формы заказа форменной одежды ВСКС (Битрикс24).
 * Прямое подключение к БД, без инфоблоков.
 *
 * Таблица создаётся автоматически при первом запросе.
 *
 * ===================== КУДА ИДУТ ДАННЫЕ =====================
 * Данные сохраняются в таблицу MySQL `uniform_orders`.
 *
 * ЭНДПОИНТЫ:
 *   POST  ajax.php?action=submit   — принять заявку (вызывается из формы)
 *   GET   ajax.php?action=orders   — посмотреть все заявки (JSON)
 *   GET   ajax.php?action=export   — скачать все заявки в CSV (открывается в Excel)
 *
 * Пример ссылок (подставьте свой домен):
 *   https://ваш-сайт.ru/uniform/ajax.php?action=export   — скачать CSV
 *   https://ваш-сайт.ru/uniform/ajax.php?action=orders   — JSON все заявки
 * =============================================================
 */

// Подключаем ядро Битрикса для доступа к БД-настройкам
require_once $_SERVER['DOCUMENT_ROOT'] . '/bitrix/modules/main/include/prolog_before.php';

header('Content-Type: application/json; charset=utf-8');

// ---------- Настройки БД ----------
// Берём из Битрикса или задаём вручную
$dbHost = defined('BX_DB_HOST') ? BX_DB_HOST : 'localhost';
$dbName = defined('BX_DB_NAME') ? BX_DB_NAME : 'bitrix';
$dbUser = defined('BX_DB_LOGIN') ? BX_DB_LOGIN : 'bitrix';
$dbPass = defined('BX_DB_PASSWORD') ? BX_DB_PASSWORD : '';

// Если константы Битрикса недоступны, читаем из dbconn.php
if ($dbHost === 'localhost' && !defined('BX_DB_HOST')) {
    $dbconnPath = $_SERVER['DOCUMENT_ROOT'] . '/bitrix/php_interface/dbconn.php';
    if (file_exists($dbconnPath)) {
        // Переменные $DBHost, $DBName, $DBLogin, $DBPassword определены в dbconn.php
        include $dbconnPath;
        $dbHost = $DBHost ?? 'localhost';
        $dbName = $DBName ?? 'bitrix';
        $dbUser = $DBLogin ?? 'bitrix';
        $dbPass = $DBPassword ?? '';
    }
}

try {
    $pdo = new PDO(
        "mysql:host={$dbHost};dbname={$dbName};charset=utf8mb4",
        $dbUser,
        $dbPass,
        [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]
    );
} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['error' => 'DB connection failed: ' . $e->getMessage()]);
    exit;
}

// ---------- Автосоздание таблицы ----------
$pdo->exec("
    CREATE TABLE IF NOT EXISTS `uniform_orders` (
        `id`         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        `region`     VARCHAR(255) NOT NULL,
        `last_name`  VARCHAR(255) NOT NULL,
        `first_name` VARCHAR(255) NOT NULL,
        `middle_name` VARCHAR(255) NOT NULL DEFAULT '',
        `address`    VARCHAR(500) NOT NULL DEFAULT '',
        `phone`      VARCHAR(50)  NOT NULL,
        `item`       VARCHAR(255) NOT NULL,
        `size`       VARCHAR(10)  NOT NULL DEFAULT '-',
        `height`     VARCHAR(10)  NOT NULL DEFAULT '-',
        `qty`        INT UNSIGNED NOT NULL DEFAULT 0
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
");

// ---------- Роутинг ----------
$action = $_GET['action'] ?? $_POST['action'] ?? '';

switch ($action) {

    // ---- Отправка заявки ----
    case 'submit':
        $input = json_decode(file_get_contents('php://input'), true);

        if (!$input || empty($input['rows'])) {
            http_response_code(400);
            echo json_encode(['error' => 'No data']);
            exit;
        }

        $region     = trim($input['region'] ?? '');
        $lastName   = trim($input['lastName'] ?? '');
        $firstName  = trim($input['firstName'] ?? '');
        $middleName = trim($input['middleName'] ?? '');
        $address    = trim($input['address'] ?? '');
        $phone      = trim($input['phone'] ?? '');

        if (!$region || !$lastName || !$firstName || !$phone) {
            http_response_code(400);
            echo json_encode(['error' => 'Missing required fields']);
            exit;
        }

        $stmt = $pdo->prepare("
            INSERT INTO `uniform_orders`
                (`region`, `last_name`, `first_name`, `middle_name`, `address`, `phone`, `item`, `size`, `height`, `qty`)
            VALUES
                (:region, :last_name, :first_name, :middle_name, :address, :phone, :item, :size, :height, :qty)
        ");

        $insertedIds = [];

        foreach ($input['rows'] as $row) {
            $stmt->execute([
                ':region'      => $region,
                ':last_name'   => $lastName,
                ':first_name'  => $firstName,
                ':middle_name' => $middleName,
                ':address'     => $address,
                ':phone'       => $phone,
                ':item'        => $row['item'] ?? '',
                ':size'        => $row['size'] ?? '-',
                ':height'      => $row['height'] ?? '-',
                ':qty'         => (int)($row['qty'] ?? 0),
            ]);
            $insertedIds[] = $pdo->lastInsertId();
        }

        echo json_encode([
            'id'     => $insertedIds[0] ?? 0,
            'count'  => count($insertedIds),
            'status' => 'ok',
        ]);
        break;

    // ---- Просмотр всех заявок (админ) ----
    case 'orders':
        $rows = $pdo->query("SELECT * FROM `uniform_orders` ORDER BY `created_at` DESC")->fetchAll();
        echo json_encode($rows, JSON_UNESCAPED_UNICODE);
        break;

    // ---- Экспорт CSV ----
    case 'export':
        $rows = $pdo->query("SELECT * FROM `uniform_orders` ORDER BY `id`")->fetchAll();

        header('Content-Type: text/csv; charset=utf-8');
        header('Content-Disposition: attachment; filename="uniform_orders.csv"');

        $out = fopen('php://output', 'w');
        // BOM для Excel
        fwrite($out, "\xEF\xBB\xBF");
        fputcsv($out, ['ID', 'Дата', 'Регион', 'Фамилия', 'Имя', 'Отчество',
                        'Адрес СДЭК', 'Телефон', 'Наименование', 'Размер', 'Рост', 'Количество'], ';');

        foreach ($rows as $r) {
            fputcsv($out, [
                $r['id'], $r['created_at'], $r['region'],
                $r['last_name'], $r['first_name'], $r['middle_name'],
                $r['address'], $r['phone'],
                $r['item'], $r['size'], $r['height'], $r['qty'],
            ], ';');
        }
        fclose($out);
        exit;

    default:
        http_response_code(400);
        echo json_encode(['error' => 'Unknown action. Use: submit, orders, export']);
}
