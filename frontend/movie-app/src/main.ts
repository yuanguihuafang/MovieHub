import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './app/router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './app-theme.css'
import './styles/movie-detail-dialog.css'
import './styles/sub-dialog.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'

const app = createApp(App)
const pinia = createPinia()

// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(pinia)
app.use(router)
app.use(ElementPlus)

app.mount('#app')
