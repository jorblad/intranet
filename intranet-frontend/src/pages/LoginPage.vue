<template>
  <div class="q-pa-md">
    <!-- Check if the user is already authenticated -->
    <div v-if="isAuthenticated()">
      <p>{{$t('login.already_logged_in')}}</p>
      <q-btn :label="$t('login.logout')" color="negative" @click="logout" />
    </div>
    <div v-else>
      <!-- Display the login form -->
      <q-form @submit.prevent="login">
        <q-input v-model="username" :label="$t('login.username')" :input-attrs="{ autocomplete: 'username' }" />
        <q-input v-model="password" type="password" :label="$t('login.password')" :input-attrs="{ autocomplete: 'current-password' }" />
        <!-- Display error message if it exists -->
        <p v-if="errorMessage" class="text-negative">{{ errorMessage }}</p>
        <q-btn type="submit" :label="$t('login.submit')" color="primary" />
      </q-form>
    </div>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  data() {
    return {
      username: '',
      password: '',
      errorMessage: '',
    };
  },
  methods: {
    async login() {

      // First attempt the authentication request. Only handle request errors here.
      let access_token, refresh_token;
      try {
        const formData = new FormData();
        formData.append('username', this.username);
        formData.append('password', this.password);
        formData.append('grant_type', 'password');
        formData.append('client_id', 'frontend');

        const response = await axios.post('/oauth/token', formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        });

        access_token = response.data.access_token;
        refresh_token = response.data.refresh_token;

        // Store tokens in localStorage
        localStorage.setItem('access_token', access_token);
        localStorage.setItem('refresh_token', refresh_token);

        // clear any previous error
        this.errorMessage = '';
      } catch (error) {
        console.error('Login request failed:', error);
        this.errorMessage = 'Fel användarnamn eller lösenord'; // Set error message
        return;
      }

      // Navigation should be attempted after successful authentication. Navigation
      // errors (for example incorrect route name) should not be treated as login
      // failures that would overwrite valid tokens, so handle them separately.
      try {
        // Use the named route `index` defined in router/routes.js
        await this.$router.push({ name: 'index' });
      } catch (navErr) {
        // Navigation failed (maybe route name mismatch). Log and fall back to path.
        console.warn('Navigation after login failed, falling back to path:', navErr);
        try { await this.$router.push('/'); } catch (e) { console.warn('Fallback navigation also failed', e); }
      }
    },
    isAuthenticated() {
      // Check if the access token is present in localStorage
      return localStorage.getItem('access_token') !== null;
    },
    logout() {
      // Remove tokens from localStorage and redirect to login page
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      // The login route in router/routes.js is at path `/login` (no name), so push by path.
      this.$router.push('/login').catch(() => {});
    },
  },
};
</script>
