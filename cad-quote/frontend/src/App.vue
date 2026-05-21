<template>
  <el-container class="app-root">
    <el-header class="app-header">
      <div class="brand">CAD 报价工具</div>
      <el-tabs v-model="activeTab" class="nav-tabs">
        <el-tab-pane label="📐 框选与报价" name="quote" />
        <el-tab-pane label="📚 型号库管理" name="catalog" />
      </el-tabs>
    </el-header>
    <el-main>
      <QuoteView v-if="activeTab === 'quote'" />
      <CatalogView v-else />
    </el-main>
  </el-container>
</template>

<script setup>
import { ref } from 'vue'
import QuoteView from './views/QuoteView.vue'
import CatalogView from './views/CatalogView.vue'

const activeTab = ref('quote')
</script>

<style>
html,
body,
#app {
  height: 100%;
  margin: 0;
  font-family: -apple-system, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;
}
.app-root {
  height: 100vh;
}
.app-header {
  display: flex;
  align-items: center;
  gap: 24px;
  background: #001529;
  color: #fff;
  border-bottom: 1px solid #333;
}
.brand {
  font-weight: 600;
  font-size: 18px;
  white-space: nowrap;
}
.nav-tabs :deep(.el-tabs__item) {
  color: #ddd !important;
}
.nav-tabs :deep(.el-tabs__item.is-active) {
  color: #fff !important;
}
.nav-tabs :deep(.el-tabs__nav-wrap)::after {
  background: transparent;
}
</style>
