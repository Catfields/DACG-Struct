<template>
  <div class="login-wrapper">
    <div class="login-card">
      <h1 class="login-title">胸片影像智能分割与报告生成系统</h1>
      <p class="login-subtitle">用户登录</p>

      <div class="login-form">
        <div class="form-row">
          <label>用户名：</label>
          <input v-model="username" placeholder="请输入用户名" />
        </div>
        <div class="form-row">
          <label>密码：</label>
          <input
            v-model="password"
            type="password"
            placeholder="请输入密码"
          />
        </div>
        <div class="form-row">
          <label>身份：</label>
          <select v-model="roleName">
            <option value="影像科医生">影像科医生</option>
            <option value="主治医生">主治医生</option>
            <option value="管理员">管理员</option>
          </select>
        </div>

        <div class="login-error" v-if="error">{{ error }}</div>

        <button class="login-btn" @click="onLogin">登录</button>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  error: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['login'])

const username = ref('')
const password = ref('')
const roleName = ref('影像科医生')

function onLogin() {
  emit('login', {
    username: username.value.trim(),
    password: password.value,
    roleName: roleName.value,
  })
}
</script>

<style scoped>
.login-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.login-card {
  width: 420px;
  padding: 32px 36px 28px;
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.18);
  box-sizing: border-box;
}

.login-title {
  margin: 0 0 4px;
  font-size: 22px;
  text-align: center;
}

.login-subtitle {
  margin: 0 0 16px;
  font-size: 14px;
  color: #6b7280;
  text-align: center;
}

.login-form {
  font-size: 14px;
}

.form-row {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.form-row label {
  width: 70px;
  color: #4b5563;
}

.form-row input,
.form-row select {
  flex: 1;
  height: 32px;
  padding: 0 8px;
  border-radius: 4px;
  border: 1px solid #cbd5e1;
  box-sizing: border-box;
}

.login-error {
  color: #dc2626;
  font-size: 13px;
  margin-bottom: 8px;
}

.login-btn {
  width: 100%;
  height: 36px;
  border-radius: 4px;
  border: none;
  background: #0ea5e9;
  color: #ffffff;
  cursor: pointer;
  margin-top: 4px;
  margin-bottom: 8px;
  font-size: 14px;
}

</style>
