import { api } from './client'

export interface Token {
  access_token: string
  token_type: string
}

export interface SSOConnection {
  id: string
  provider_id: string
  provider_name: string
  provider_display_name: string
  provider_icon_url: string | null
  provider_user_id: string
  provider_username: string | null
  provider_email: string | null
  first_login: string
  last_login: string
}

export interface User {
  id: string
  username: string
  email: string
  is_active: boolean
  is_superuser: boolean
  email_verified: boolean
  avatar_url: string | null
  locale: string
  created_at: string
  last_login: string | null
  auth_source: string
  external_id: string | null
  roles: Role[]
  sso_connections: SSOConnection[]
}

export interface Role {
  id: string
  name: string
  description: string | null
  is_system_role: boolean
  permissions: Permission[]
}

export interface Permission {
  id: string
  scope: string
  code: string
  description: string | null
}

export interface RegisterData {
  username: string
  email: string
  password: string
}

export interface VerificationResponse {
  verified: boolean
  email: string | null
}

export interface CaptchaResponse {
  captcha_id: string
  question: string
}

export interface LoginData {
  username: string
  password: string
  captcha_id?: string
  captcha_answer?: string
}

export const authApi = {
  /**
   * 获取验证码
   */
  getCaptcha: async (): Promise<CaptchaResponse> => {
    return api.get<CaptchaResponse>('/captcha')
  },

  /**
   * 登录获取 token
   */
  login: async (data: LoginData): Promise<Token> => {
    const formData = new FormData()
    formData.append('username', data.username)
    formData.append('password', data.password)
    if (data.captcha_id) {
      formData.append('captcha_id', data.captcha_id)
    }
    if (data.captcha_answer) {
      formData.append('captcha_answer', data.captcha_answer)
    }
    return api.postForm<Token>('/login/access-token', formData, { skipAuthRedirect: true })
  },

  /**
   * 注销登录
   */
  logout: async (): Promise<void> => {
    await api.post<null>('/logout')
  },

  /**
   * 注册新用户
   */
  register: async (data: RegisterData): Promise<User> => {
    return api.post<User>('/register', data)
  },

  /**
   * 获取当前用户信息
   */
  getCurrentUser: async (options?: { skipAuthRedirect?: boolean }): Promise<User> => {
    return api.get<User>('/users/me', { skipAuthRedirect: options?.skipAuthRedirect })
  },

  /**
   * 发送邮箱验证邮件
   */
  sendVerification: async (email: string, purpose: string = 'register'): Promise<void> => {
    await api.post<null>('/send-verification', { email, purpose })
  },

  /**
   * 重新发送验证邮件
   */
  resendVerification: async (email: string): Promise<void> => {
    await api.post<null>('/resend-verification', { email })
  },

  /**
   * 验证邮箱验证码
   */
  verifyEmail: async (email: string, code: string, purpose: string = 'register'): Promise<VerificationResponse> => {
    return api.post<VerificationResponse>('/verify-email', { email, code, purpose })
  },

  /**
   * 通过 token 验证邮箱
   */
  verifyEmailByToken: async (token: string): Promise<VerificationResponse> => {
    return api.get<VerificationResponse>(`/verify?token=${token}`)
  },

  /**
   * 发送忘记密码邮件
   */
  forgotPassword: async (email: string): Promise<void> => {
    await api.post<null>('/forgot-password', { email })
  },

  /**
   * 重置密码
   */
  resetPassword: async (email: string, code: string, newPassword: string): Promise<void> => {
    await api.post<null>('/reset-password', { email, code, new_password: newPassword })
  },
}
