import axios from 'axios'

let isRefreshing = false
let refreshPromise = null
let subscribers = []

function onRefreshed(token) {
  subscribers.forEach(cb => cb(token))
  subscribers = []
}

function addSubscriber(cb) {
  subscribers.push(cb)
}

export function setupInterceptors({ refreshEndpoint = '/oauth/token' } = {}) {
  // request: attach access token if present
  axios.interceptors.request.use((config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers = config.headers || {}
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  })

  // response: if 401, try refresh token flow
  axios.interceptors.response.use(
    (res) => res,
    async (error) => {
      const originalRequest = error.config
      if (!originalRequest) return Promise.reject(error)

      // if already tried refresh for this request, reject
      if (error.response && error.response.status === 401 && !originalRequest._retry) {
        originalRequest._retry = true
        const refreshToken = localStorage.getItem('refresh_token')
        if (!refreshToken) {
          // no refresh available: clear any tokens and redirect to login
          try {
            localStorage.removeItem('access_token')
            localStorage.removeItem('refresh_token')
          } catch (e) {}
          if (typeof window !== 'undefined') {
            try {
              const location = window.location || {}
              const hash = String(location.hash || '')
              const pathname = String(location.pathname || '')
              if (!hash.includes('/invite/accept') && !pathname.includes('/invite/accept')) {
                window.location.href = '/login'
              }
            } catch (e) {}
          }
          return Promise.reject(error)
        }

        if (!isRefreshing) {
          isRefreshing = true
          refreshPromise = axios.post(refreshEndpoint, new URLSearchParams({ grant_type: 'refresh_token', refresh_token: refreshToken }), {
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          }).then(res => {
            const data = res.data
            if (data.access_token) {
              localStorage.setItem('access_token', data.access_token)
            }
            if (data.refresh_token) {
              localStorage.setItem('refresh_token', data.refresh_token)
            }
            onRefreshed(data.access_token)
            return data
          }).catch(err => {
            // refresh failed: clear tokens and redirect to login
            try {
              localStorage.removeItem('access_token')
              localStorage.removeItem('refresh_token')
            } catch (e) {}
            if (typeof window !== 'undefined') {
              try {
                const location = window.location || {}
                const hash = String(location.hash || '')
                const pathname = String(location.pathname || '')
                if (!hash.includes('/invite/accept') && !pathname.includes('/invite/accept')) {
                  window.location.href = '/login'
                }
              } catch (e) {}
            }
            throw err
          }).finally(() => {
            isRefreshing = false
            refreshPromise = null
          })
        }

        return new Promise((resolve, reject) => {
          addSubscriber((token) => {
            if (token) {
              originalRequest.headers['Authorization'] = `Bearer ${token}`
              resolve(axios(originalRequest))
            } else {
              reject(error)
            }
          })
        })
      }

      return Promise.reject(error)
    }
  )
}

export default axios
