<template>
  <div class="admin-shell">
    <header class="admin-top">
      <div class="inner">
        <router-link to="/" class="brand">
          <span class="brand-mark">MH</span>
          <span class="brand-text">MovieHub · 管理后台</span>
        </router-link>
        <div class="nav-right">
          <router-link to="/" class="back-chip">返回</router-link>
        </div>
      </div>
    </header>

    <main class="admin-body">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.admin-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(1100px 520px at 12% -10%, rgba(99, 102, 241, 0.18), transparent 55%),
    radial-gradient(900px 520px at 90% 0%, rgba(168, 85, 247, 0.12), transparent 52%),
    #070b1a;
}

.admin-top {
  position: sticky;
  top: 0;
  z-index: 50;
  backdrop-filter: blur(16px) saturate(1.2);
  background: linear-gradient(180deg, rgba(7, 11, 26, 0.78), rgba(7, 11, 26, 0.46));
  border-bottom: 1px solid rgba(255, 255, 255, 0.09);
}

.inner {
  max-width: 1240px;
  margin: 0 auto;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  height: 64px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  color: rgba(255, 255, 255, 0.92);
  font-weight: 800;
  letter-spacing: 0.02em;
}

.brand-mark {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: linear-gradient(135deg, #fb923c, #a855f7);
  color: #fff;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.12) inset,
    0 10px 28px rgba(0, 0, 0, 0.25);
}

.brand-text {
  font-size: 18px;
}

.back-chip {
  display: inline-flex;
  align-items: center;
  padding: 8px 14px;
  border-radius: 999px;
  color: rgba(255, 255, 255, 0.92);
  text-decoration: none;
  background: rgba(99, 102, 241, 0.14);
  border: 1px solid rgba(99, 102, 241, 0.2);
}

.admin-body {
  flex: 1;
  width: 100%;
}
</style>

