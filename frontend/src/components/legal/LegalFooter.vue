<template>
  <footer class="legal-footer">
    <div class="legal-footer-inner">

      <div class="legal-footer-col">
        <div class="legal-footer-brand">
          <v-icon icon="mdi-account-cash" color="primary" size="20" />
          <span>GALA</span>
        </div>
        <div class="legal-footer-requisites">
          <div v-if="operator.fullName">{{ operator.fullName }}</div>
          <div v-if="operator.inn">ИНН {{ operator.inn }}</div>
          <div v-if="operator.ogrn">ОГРН {{ operator.ogrn }}</div>
          <!-- Оператор-физлицо: адрес в реквизитах — домашний адрес владельца;
               он остаётся в тексте политики (где это юридически обязательно),
               но не выводится в подвале каждой страницы сайта. -->
          <div v-if="operator.legalAddress && operator.form !== 'физическое лицо'">{{ operator.legalAddress }}</div>
          <div v-if="operator.supportEmail">
            <a :href="`mailto:${operator.supportEmail}`">{{ operator.supportEmail }}</a>
          </div>
        </div>
      </div>

      <div class="legal-footer-col">
        <div class="legal-footer-title">Правовые документы</div>
        <ul class="legal-footer-links">
          <li v-for="d in docs" :key="d.slug">
            <router-link :to="d.route">{{ d.title }}</router-link>
          </li>
        </ul>
      </div>

    </div>

    <div class="legal-footer-bottom">
      <span>© {{ year }} {{ operator.fullName || 'GALA' }}</span>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { LEGAL_DOC_LIST, OPERATOR } from '@/legal/documents.generated'

const operator = OPERATOR
const docs = LEGAL_DOC_LIST
const year = new Date().getFullYear()
</script>

<style scoped>
/* Переменные --text/--text-2/--text-3/--border/--bg заданы родителем (LandingView
   задаёт их на .landing-light/.landing-dark) — CSS-custom-properties наследуются
   через DOM независимо от scoped-атрибутов компонентов. На случай использования
   footer'а вне лендинга — запасные значения через var(x, fallback). */
.legal-footer {
  padding: 32px 24px 20px;
  border-top: 1px solid var(--border, rgba(0, 0, 0, 0.08));
  background: var(--bg, transparent);
}
.legal-footer-inner {
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 32px;
}
.legal-footer-col {
  min-width: 220px;
}
.legal-footer-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text, inherit);
  margin-bottom: 12px;
}
.legal-footer-requisites {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text-3, rgba(0, 0, 0, 0.5));
}
.legal-footer-requisites a {
  color: var(--text-3, rgba(0, 0, 0, 0.5));
  text-decoration: none;
}
.legal-footer-requisites a:hover {
  text-decoration: underline;
}
.legal-footer-title {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-2, rgba(0, 0, 0, 0.6));
  margin-bottom: 12px;
}
.legal-footer-links {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.legal-footer-links a {
  font-size: 13px;
  color: var(--text-2, rgba(0, 0, 0, 0.6));
  text-decoration: none;
}
.legal-footer-links a:hover {
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
}
.legal-footer-bottom {
  max-width: 1100px;
  margin: 24px auto 0;
  padding-top: 16px;
  border-top: 1px solid var(--border, rgba(0, 0, 0, 0.08));
  font-size: 12px;
  color: var(--text-3, rgba(0, 0, 0, 0.5));
}

@media (max-width: 600px) {
  .legal-footer-inner {
    flex-direction: column;
    gap: 24px;
  }
}
</style>
