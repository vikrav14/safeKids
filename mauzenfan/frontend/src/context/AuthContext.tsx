// src/contexts/AuthContext.tsx
import React, { createContext, useState, useEffect, useContext, ReactNode } from 'react';
import api from '../api';

// Define types for better TypeScript support
interface User {
  id: number;
  username: string;
  email: string;
  first_name?: string;
  last_name?: string;
  // Add other user properties as needed
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  error: string | null;
  login: (credentials: { username: string; password: string }) => Promise<boolean>;
  logout: () => Promise<void>;
  register: (userData: {
    username: string;
    email: string;
    password: string;
    first_name?: string;
    last_name?: string;
  }) => Promise<boolean>;
  isAuthenticated: boolean;
}

// Create context with default values
const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: false,
  error: null,
  login: async () => false,
  logout: async () => {},
  register: async () => false,
  isAuthenticated: false,
});

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider = ({ children }: AuthProviderProps) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Initialize authentication check
  useEffect(() => {
    const token = localStorage.getItem('authToken');
    
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`; // Changed to Bearer
    }
    
    const checkAuth = async () => {
      try {
        // CORRECTED ENDPOINT: Changed to Djoser's actual user endpoint
        const response = await api.get('/api/auth/users/me/');
        if (response.data) {
          setUser(response.data);
        }
      } catch (err) {
        console.error('Auth check error:', err);
      } finally {
        setLoading(false);
      }
    };
    
    checkAuth();
  }, []);

  // Login function
  const login = async (credentials: { username: string; password: string }): Promise<boolean> => {
    setLoading(true);
    setError(null);
    
    try {
      // CORRECTED ENDPOINT: Changed to Djoser's JWT create endpoint
      const response = await api.post('/api/auth/jwt/create/', credentials);
      
      // Store token and set headers
      const { access } = response.data; // Extract access token
      localStorage.setItem('authToken', access);
      api.defaults.headers.common['Authorization'] = `Bearer ${access}`;
      
      // Fetch user profile after successful login
      const userResponse = await api.get('/api/auth/users/me/');
      setUser(userResponse.data);
      return true;
    } catch (err: any) {
      setError(err?.response?.data?.error || 'Login failed');
      return false;
    } finally {
      setLoading(false);
    }
  };

  // Register function
  const register = async (userData: {
    username: string;
    email: string;
    password: string;
    first_name?: string;
    last_name?: string;
  }): Promise<boolean> => {
    setLoading(true);
    setError(null);
    
    try {
      // CORRECTED ENDPOINT: Changed to Djoser's user registration endpoint
      await api.post('/api/auth/users/', userData);
      
      // Automatically login after registration
      return await login({
        username: userData.username,
        password: userData.password
      });
    } catch (err: any) {
      setError(
        err?.response?.data?.error ||
        err?.response?.data?.message ||
        'Registration failed'
      );
      return false;
    }
  };

  // Logout function
  const logout = async (): Promise<void> => {
    // No logout endpoint needed for JWT - just clear local data
    localStorage.removeItem('authToken');
    delete api.defaults.headers.common['Authorization'];
    setUser(null);
  };

  // Value to provide to consumers
  const value: AuthContextType = {
    user,
    loading,
    error,
    login,
    logout,
    register,
    isAuthenticated: !!user
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

// Custom hook for easy access
export const useAuth = () => useContext(AuthContext);