import axios from 'axios'
import { getSession } from '../auth/auth'

const api = axios.create({ baseURL: '/api' })

// Attach the role header on every request so the backend role guard works.
api.interceptors.request.use(config => {
  const s = getSession()
  if (s?.role) config.headers['X-Role'] = s.role
  return config
})

export default api
