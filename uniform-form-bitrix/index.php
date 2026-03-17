<?php
// Подключаем шапку Битрикса (меню, стили сайта)
require $_SERVER['DOCUMENT_ROOT'] . '/bitrix/header.php';
$APPLICATION->SetTitle('Заказ форменной одежды ВСКС');
?>

<style>
  .uf-wrap * { box-sizing: border-box; }
  .uf-wrap { font-family: 'Segoe UI', Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px 0; }
  .uf-card { background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
  .uf-info { background: #e8f4fd; border-left: 4px solid #2196F3; padding: 12px 16px; border-radius: 0 8px 8px 0; margin-bottom: 20px; font-size: 14px; color: #1565C0; }
  .uf-wrap label { display: block; font-weight: 600; margin-bottom: 4px; color: #333; font-size: 13px; }
  .uf-wrap input, .uf-wrap select { width: 100%; padding: 9px 10px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; transition: border-color 0.2s; }
  .uf-wrap input:focus, .uf-wrap select:focus { outline: none; border-color: #2196F3; box-shadow: 0 0 0 3px rgba(33,150,243,0.1); }
  .uf-top { display: flex; flex-wrap: wrap; gap: 16px; }
  .uf-top > div { flex: 1; min-width: 200px; }
  .uf-section { font-size: 16px; font-weight: 700; margin-bottom: 12px; color: #1a1a2e; }
  .uf-divider { border: none; border-top: 2px solid #e0e0e0; margin: 20px 0; }
  .uf-row { background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 10px; padding: 16px; margin-bottom: 12px; position: relative; }
  .uf-row .uf-grid { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; }
  .uf-row .uf-grid > div { min-width: 130px; flex: 1; }
  .uf-row .uf-grid > div.col-item { min-width: 200px; flex: 2; }
  .uf-row .uf-grid > div.col-size,
  .uf-row .uf-grid > div.col-height { min-width: 100px; flex: 0.7; }
  .uf-row .uf-grid > div.col-qty { min-width: 90px; flex: 0.5; }
  .uf-rownum { position: absolute; top: -10px; left: 12px; background: #2196F3; color: #fff; font-size: 12px; padding: 2px 10px; border-radius: 10px; font-weight: 600; }
  .uf-btn { padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; transition: all 0.2s; }
  .uf-btn-add { background: #e8f5e9; color: #2e7d32; }
  .uf-btn-add:hover { background: #c8e6c9; }
  .uf-btn-rm { background: #ffebee; color: #c62828; position: absolute; top: 8px; right: 8px; padding: 4px 10px; font-size: 12px; }
  .uf-btn-rm:hover { background: #ffcdd2; }
  .uf-btn-submit { background: #1976D2; color: #fff; width: 100%; padding: 14px; font-size: 16px; margin-top: 20px; }
  .uf-btn-submit:hover { background: #1565C0; }
  .uf-btn-submit:disabled { background: #bbb; cursor: not-allowed; }
  .uf-toast { position: fixed; top: 20px; right: 20px; padding: 16px 24px; border-radius: 10px; color: #fff; font-weight: 600; z-index: 9999; transform: translateX(120%); transition: transform 0.3s; max-width: 400px; }
  .uf-toast.show { transform: translateX(0); }
  .uf-toast.success { background: #43a047; }
  .uf-toast.error { background: #e53935; }
  .uf-preview { background: #fafafa; border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px; margin-top: 16px; font-size: 12px; overflow-x: auto; }
  .uf-preview table { width: 100%; border-collapse: collapse; }
  .uf-preview th, .uf-preview td { border: 1px solid #ddd; padding: 5px 8px; text-align: left; }
  .uf-preview th { background: #e3f2fd; white-space: nowrap; }
  .uf-hidden { display: none !important; }
</style>

<div class="uf-wrap">
  <div class="uf-card">
    <div class="uf-info">
      Сначала заполните ваши данные (регион, ФИО, адрес СДЭК, телефон).<br>
      Затем добавьте позиции заказа. Для петлиц и нашивок размер и рост не требуются.
    </div>

    <div class="uf-section">Данные получателя</div>
    <div class="uf-top">
      <div>
        <label>Регион</label>
        <select id="uf-region"><option value="">— Выберите регион —</option></select>
      </div>
      <div>
        <label>Фамилия получающего</label>
        <input type="text" id="uf-lastName" placeholder="Иванов">
      </div>
      <div>
        <label>Имя получающего</label>
        <input type="text" id="uf-firstName" placeholder="Иван">
      </div>
      <div>
        <label>Отчество получающего</label>
        <input type="text" id="uf-middleName" placeholder="Иванович">
      </div>
      <div>
        <label>Адрес пункта выдачи СДЭК с городом</label>
        <input type="text" id="uf-address" placeholder="г. Москва, ул. Примерная, 1">
      </div>
      <div>
        <label>Телефон получающего</label>
        <input type="tel" id="uf-phone" placeholder="+7 (999) 123-45-67">
      </div>
    </div>

    <hr class="uf-divider">

    <div class="uf-section">Позиции заказа</div>
    <div id="uf-rows"></div>

    <div style="margin-top:8px;">
      <button class="uf-btn uf-btn-add" onclick="ufAddRow()">+ Добавить позицию</button>
    </div>

    <div id="uf-preview"></div>

    <button class="uf-btn uf-btn-submit" id="uf-submit" onclick="ufSubmit()">Отправить заявку</button>
  </div>
</div>

<div class="uf-toast" id="uf-toast"></div>

<script>
(function() {
  const REGIONS = [
    "Республика Адыгея","Республика Алтай","Республика Башкортостан","Республика Бурятия",
    "Республика Дагестан","Республика Ингушетия","Кабардино-Балкарская Республика",
    "Республика Калмыкия","Карачаево-Черкесская Республика","Республика Карелия",
    "Республика Коми","Республика Крым","Республика Марий Эл","Республика Мордовия",
    "Республика Саха (Якутия)","Республика Северная Осетия — Алания","Республика Татарстан",
    "Республика Тыва","Удмуртская Республика","Республика Хакасия","Чеченская Республика",
    "Чувашская Республика","Алтайский край","Забайкальский край","Камчатский край",
    "Краснодарский край","Красноярский край","Пермский край","Приморский край",
    "Ставропольский край","Хабаровский край","Амурская область","Архангельская область",
    "Астраханская область","Белгородская область","Брянская область","Владимирская область",
    "Волгоградская область","Вологодская область","Воронежская область","Ивановская область",
    "Иркутская область","Калининградская область","Калужская область","Кемеровская область — Кузбасс",
    "Кировская область","Костромская область","Курганская область","Курская область",
    "Ленинградская область","Липецкая область","Магаданская область","Московская область",
    "Мурманская область","Нижегородская область","Новгородская область","Новосибирская область",
    "Омская область","Оренбургская область","Орловская область","Пензенская область",
    "Псковская область","Ростовская область","Рязанская область","Самарская область",
    "Саратовская область","Сахалинская область","Свердловская область","Смоленская область",
    "Тамбовская область","Тверская область","Томская область","Тульская область",
    "Тюменская область","Ульяновская область","Челябинская область","Ярославская область",
    "Москва","Санкт-Петербург","Севастополь",
    "Еврейская автономная область",
    "Ненецкий автономный округ","Ханты-Мансийский автономный округ — Югра",
    "Чукотский автономный округ","Ямало-Ненецкий автономный округ",
    "Донецкая Народная Республика","Луганская Народная Республика",
    "Запорожская область","Херсонская область"
  ];

  const ITEMS = ["Габардин ВСКС","Комбинезон","Петлица (1штука)","Нашивка-Доброволец ЧС","Нашивка-ВСКС"];
  const NO_SIZE = ["Петлица (1штука)","Нашивка-Доброволец ЧС","Нашивка-ВСКС"];
  const SIZES = ["34","36","38","40","42","44","46","48","50","52","54","56","58","60","62"];
  const HEIGHTS = ["146","152","158","164","170","176","182","188","194"];
  const QTY = []; for (let i=0;i<=20;i++) QTY.push(String(i));

  // Fill regions
  const rSel = document.getElementById('uf-region');
  REGIONS.forEach(r => { const o=document.createElement('option'); o.value=r; o.textContent=r; rSel.appendChild(o); });

  let rowN = 0;

  function opts(arr, ph) {
    let h = '<option value="">'+ph+'</option>';
    arr.forEach(v => h += '<option value="'+v+'">'+v+'</option>');
    return h;
  }

  window.ufAddRow = function() {
    rowN++;
    const d = document.createElement('div');
    d.className = 'uf-row'; d.id = 'uf-r-'+rowN;
    d.innerHTML = '<span class="uf-rownum">'+rowN+'</span>'
      + (rowN>1 ? '<button class="uf-btn uf-btn-rm" onclick="ufRemoveRow(\'uf-r-'+rowN+'\')">Удалить</button>' : '')
      + '<div class="uf-grid">'
      + '<div class="col-item"><label>Наименование</label><select class="fi" onchange="ufItemChg(this)">'+opts(ITEMS,'— Выберите —')+'</select></div>'
      + '<div class="col-size"><label>Размер</label><select class="fs" onchange="ufPreview()">'+opts(SIZES,'—')+'</select></div>'
      + '<div class="col-height"><label>Рост</label><select class="fh" onchange="ufPreview()">'+opts(HEIGHTS,'—')+'</select></div>'
      + '<div class="col-qty"><label>Количество</label><select class="fq" onchange="ufPreview()">'+opts(QTY,'—')+'</select></div>'
      + '</div>';
    document.getElementById('uf-rows').appendChild(d);
    ufPreview();
  };

  window.ufRemoveRow = function(id) {
    document.getElementById(id).remove();
    document.querySelectorAll('.uf-row').forEach((el,i) => el.querySelector('.uf-rownum').textContent = i+1);
    ufPreview();
  };

  window.ufItemChg = function(sel) {
    const row = sel.closest('.uf-row');
    const noSz = NO_SIZE.includes(sel.value);
    row.querySelector('.col-size').classList.toggle('uf-hidden', noSz);
    row.querySelector('.col-height').classList.toggle('uf-hidden', noSz);
    if (noSz) { row.querySelector('.fs').value='-'; row.querySelector('.fh').value='-'; }
    else { if(row.querySelector('.fs').value==='-') row.querySelector('.fs').value=''; if(row.querySelector('.fh').value==='-') row.querySelector('.fh').value=''; }
    ufPreview();
  };

  function getTop() {
    return {
      region: document.getElementById('uf-region').value,
      lastName: document.getElementById('uf-lastName').value.trim(),
      firstName: document.getElementById('uf-firstName').value.trim(),
      middleName: document.getElementById('uf-middleName').value.trim(),
      address: document.getElementById('uf-address').value.trim(),
      phone: document.getElementById('uf-phone').value.trim()
    };
  }

  function getRows() {
    const out = [];
    document.querySelectorAll('.uf-row').forEach(el => {
      const item = el.querySelector('.fi').value;
      const noSz = NO_SIZE.includes(item);
      out.push({ item, size: noSz?'-':el.querySelector('.fs').value, height: noSz?'-':el.querySelector('.fh').value, qty: el.querySelector('.fq').value });
    });
    return out;
  }

  window.ufPreview = function() {
    const t = getTop(), rows = getRows();
    if (!rows.length) { document.getElementById('uf-preview').innerHTML=''; return; }
    let h = '<div class="uf-preview"><strong>Предпросмотр:</strong><table><tr><th>Регион</th><th>Наименование</th><th>Размер</th><th>Рост</th><th>Кол-во</th><th>Фамилия</th><th>Имя</th><th>Отчество</th><th>Адрес СДЭК</th><th>Телефон</th></tr>';
    rows.forEach(r => {
      h += '<tr><td>'+(t.region||'—')+'</td><td>'+(r.item||'—')+'</td><td>'+(r.size||'—')+'</td><td>'+(r.height||'—')+'</td><td>'+(r.qty||'—')+'</td><td>'+(t.lastName||'—')+'</td><td>'+(t.firstName||'—')+'</td><td>'+(t.middleName||'—')+'</td><td>'+(t.address||'—')+'</td><td>'+(t.phone||'—')+'</td></tr>';
    });
    h += '</table></div>';
    document.getElementById('uf-preview').innerHTML = h;
  };

  // Update preview on top field changes
  ['uf-region','uf-lastName','uf-firstName','uf-middleName','uf-address','uf-phone'].forEach(id => {
    const el = document.getElementById(id);
    el.addEventListener('input', ufPreview);
    el.addEventListener('change', ufPreview);
  });

  function toast(msg, type) {
    const t = document.getElementById('uf-toast');
    t.textContent = msg; t.className = 'uf-toast '+type+' show';
    setTimeout(() => t.classList.remove('show'), 4000);
  }

  window.ufSubmit = async function() {
    const t = getTop(), rows = getRows();
    if (!t.region) { toast('Выберите регион','error'); return; }
    if (!t.lastName) { toast('Укажите фамилию','error'); return; }
    if (!t.firstName) { toast('Укажите имя','error'); return; }
    if (!t.phone) { toast('Укажите телефон','error'); return; }
    if (!rows.length) { toast('Добавьте позицию','error'); return; }

    for (let i=0; i<rows.length; i++) {
      const r = rows[i], noSz = NO_SIZE.includes(r.item);
      if (!r.item || r.qty==='') { toast('Позиция '+(i+1)+': выберите наименование и количество','error'); return; }
      if (!noSz && (!r.size || !r.height)) { toast('Позиция '+(i+1)+': выберите размер и рост','error'); return; }
    }

    document.getElementById('uf-submit').disabled = true;
    try {
      // Данные отправляются в ajax.php -> таблица MySQL `uniform_orders`
      // Скачать все заявки CSV:  ajax.php?action=export
      // Посмотреть JSON:         ajax.php?action=orders
      const resp = await fetch('ajax.php?action=submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ region: t.region, lastName: t.lastName, firstName: t.firstName, middleName: t.middleName, address: t.address, phone: t.phone, rows })
      });
      if (!resp.ok) throw new Error();
      const data = await resp.json();
      toast('Заявка #'+data.id+' отправлена! Спасибо.','success');
      document.getElementById('uf-rows').innerHTML = '';
      rowN = 0; ufAddRow();
      document.getElementById('uf-preview').innerHTML = '';
    } catch(e) {
      toast('Ошибка отправки. Попробуйте ещё раз.','error');
    }
    document.getElementById('uf-submit').disabled = false;
  };

  ufAddRow();
})();
</script>

<?php require $_SERVER['DOCUMENT_ROOT'] . '/bitrix/footer.php'; ?>
