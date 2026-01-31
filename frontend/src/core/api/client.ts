/**
 * Axios client configuration with retry logic and error handling
 */
import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

/**
 * API Client Configuration
 */
export interface ApiClientConfig {
  baseURL: string;
  timeout: number;
  retryAttempts: number;
  retryDelay: number;
}

/**
 * Get API client configuration from environment variables
 */
const getConfig = (): ApiClientConfig => ({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'https://pharos.onrender.com',
  timeout: Number(import.meta.env.VITE_API_TIMEOUT) || 30000,
  retryAttempts: Number(import.meta.env.VITE_API_RETRY_ATTEMPTS) || 3,
  retryDelay: Number(import.meta.env.VITE_API_RETRY_DELAY) || 1000,
});

const config = getConfig();

/**
 * Clear authentication state
 * This is a helper to avoid circular dependencies with the auth store
 */
const clearAuthState = () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('neo-alexandria-auth');
  delete apiClient.defaults.headers.common['Authorization'];
};

/**
 * Create Axios instance with base configuration
 */
export const apiClient = axios.create({
  baseURL: config.baseURL,
  timeout: config.timeout,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Request interceptor - attach access token to all requests
 */
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Retrieve access token from localStorage
    const accessToken = localStorage.getItem('access_token');
    
    // If token exists, attach as Bearer token
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
    
    // Log request in development mode
    if (import.meta.env.DEV) {
      console.log(`[API Request] ${config.method?.toUpperCase()} ${config.url}`, {
        params: config.params,
        data: config.data,
      });
    }
    
    return config;
  },
  (error) => {
    // Log error in development mode
    if (import.meta.env.DEV) {
      console.error('[API Request Error]', error);
    }
    return Promise.reject(error);
  }
);

/**
 * Extended Axios request config with retry flag and attempt counter
 */
interface ExtendedAxiosRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
  _retryCount?: number;
}

/**
 * Custom error for rate limiting
 */
export interface RateLimitError extends Error {
  retryAfter?: number;
  status: number;
}

/**
 * Calculate exponential backoff delay
 */
const getRetryDelay = (retryCount: number): number => {
  return Math.min(config.retryDelay * Math.pow(2, retryCount), 30000);
};

/**
 * Determine if error is retryable
 */
const isRetryableError = (error: AxiosError): boolean => {
  // Retry on network errors
  if (!error.response) {
    return true;
  }
  
  // Retry on 5xx server errors
  const status = error.response.status;
  return status >= 500 && status < 600;
};

/**
 * Response interceptor - handle success, errors, and retries
 */
apiClient.interceptors.response.use(
  // Success path - log response and return
  (response) => {
    // Log response in development mode
    if (import.meta.env.DEV) {
      console.log(`[API Response] ${response.config.method?.toUpperCase()} ${response.config.url}`, {
        status: response.status,
        data: response.data,
      });
      
      // Note: Runtime validation happens at the API method level, not here
      // This allows each endpoint to use its specific schema validator
      // See frontend/src/lib/api/*.ts for validation usage
    }
    return response;
  },
  // Error path - handle 401, 429, and retryable errors
  async (error: AxiosError) => {
    const originalRequest = error.config as ExtendedAxiosRequestConfig;

    // Log error in development mode
    if (import.meta.env.DEV) {
      console.error('[API Response Error]', {
        url: originalRequest?.url,
        status: error.response?.status,
        message: error.message,
        data: error.response?.data,
      });
    }

    // Handle 401 - Token refresh
    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      // Set retry flag to prevent infinite loops
      originalRequest._retry = true;

      try {
        // Retrieve refresh token from localStorage
        const refreshToken = localStorage.getItem('refresh_token');

        if (!refreshToken) {
          // No refresh token available, clear auth and redirect
          clearAuthState();
          window.location.href = '/login';
          return Promise.reject(error);
        }

        // Call refresh endpoint
        const response = await axios.post(
          `${config.baseURL}/api/auth/refresh`,
          { refresh_token: refreshToken },
          {
            headers: {
              'Content-Type': 'application/json',
            },
          }
        );

        // Extract new access token
        const { access_token } = response.data;

        // Update localStorage
        localStorage.setItem('access_token', access_token);

        // Update Axios default header for all future requests
        apiClient.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;

        // Update the retry request header
        originalRequest.headers.Authorization = `Bearer ${access_token}`;

        // Retry original request
        return apiClient(originalRequest);
      } catch (refreshError) {
        // Refresh failed - clear auth state and redirect to login
        clearAuthState();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    // Handle 429 - Rate limiting
    if (error.response?.status === 429) {
      // Extract Retry-After header
      const retryAfter = error.response.headers['retry-after'];
      
      // Create custom error with retryAfter property
      const rateLimitError: RateLimitError = Object.assign(
        new Error('Rate limit exceeded'),
        {
          retryAfter: retryAfter ? parseInt(retryAfter, 10) : undefined,
          status: 429,
        }
      );
      
      return Promise.reject(rateLimitError);
    }

    // Handle retryable errors (network errors and 5xx)
    if (originalRequest && isRetryableError(error)) {
      const retryCount = originalRequest._retryCount || 0;
      
      // Check if we've exceeded retry attempts
      if (retryCount >= config.retryAttempts) {
        if (import.meta.env.DEV) {
          console.error(`[API Retry] Max retry attempts (${config.retryAttempts}) exceeded for ${originalRequest.url}`);
        }
        return Promise.reject(error);
      }
      
      // Increment retry count
      originalRequest._retryCount = retryCount + 1;
      
      // Calculate delay with exponential backoff
      const delay = getRetryDelay(retryCount);
      
      if (import.meta.env.DEV) {
        console.log(`[API Retry] Attempt ${originalRequest._retryCount}/${config.retryAttempts} for ${originalRequest.url} after ${delay}ms`);
      }
      
      // Wait for delay then retry
      await new Promise(resolve => setTimeout(resolve, delay));
      return apiClient(originalRequest);
    }

    // For all other errors, reject as-is
    return Promise.reject(error);
  }
);

/**
 * Authentication token management helpers
 */
export const setAuthToken = (token: string): void => {
  localStorage.setItem('access_token', token);
  apiClient.defaults.headers.common['Authorization'] = `Bearer ${token}`;
};

export const clearAuthToken = (): void => {
  clearAuthState();
};

export const getAuthToken = (): string | null => {
  return localStorage.getItem('access_token');
};
