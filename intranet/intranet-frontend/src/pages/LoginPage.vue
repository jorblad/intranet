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

        const access_token = response.data.access_token;
        const refresh_token = response.data.refresh_token;

        // Store tokens in localStorage
        localStorage.setItem('access_token', access_token);
        localStorage.setItem('refresh_token', refresh_token);

        // Redirect to the desired route
        this.$router.push({ name: 'schedules' }); // Change this to your route
      } catch (error) {
        console.error('Login failed:', error);
        this.errorMessage = 'Fel användarnamn eller lösenord'; // Set error message
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
      this.$router.push({ name: 'login' }); // Change this to your login route
    },
  },
};
</script>
