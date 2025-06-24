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
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Initialize authentication check
  useEffect(() => {
    const token = localStorage.getItem('authToken');
    
    if (token) {
      api.defaults.headers.common['Authorization'] = `Token ${token}`;
    }
    
    const checkAuth = async () => {
      try {
        const response = await api.get('/api/auth/me/');
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
      const response = await api.post('/api/auth/login/', credentials);
      
      // Store token and set headers
      localStorage.setItem('authToken', response.data.token);
      api.defaults.headers.common['Authorization'] = `Token ${response.data.token}`;
      
      setUser(response.data.user);
      return true;
    } catch (err) {
      setError(err.response?.data?.error || 'Login failed');
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
      const response = await api.post('/api/auth/register/', userData);
      
      // Store token and set headers
      localStorage.setItem('authToken', response.data.token);
      api.defaults.headers.common['Authorization'] = `Token ${response.data.token}`;
      
      setUser(response.data.user);
      return true;
    } catch (err) {
      setError(
        err.response?.data?.error || 
        err.response?.data?.message || 
        'Registration failed'
      );
      return false;
    } finally {
      setLoading(false);
    }
  };

  // Logout function
  const logout = async (): Promise<void> => {
    try {
      await api.post('/api/auth/logout/');
    } catch (err) {
      console.error('Logout error:', err);
    } finally {
      // Clear token and user state
      localStorage.removeItem('authToken');
      delete api.defaults.headers.common['Authorization'];
      setUser(null);
    }
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