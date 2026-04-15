import type { NextApiRequest, NextApiResponse } from 'next';
import * as crypto from 'crypto';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'https://tls-api-v2-production.up.railway.app/api/v1';

// ─── In-Memory Auth Store ────────────────────────────────────────────────────
// Module-level state persists across requests in same Vercel function instance.
// For demo / MVP — replace with DB (Supabase, PlanetScale) for production.

interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  password: string; // stored plaintext for demo; hash in prod
  role: string;
  created_at: string;
}

const USERS: Record<string, User> = {};           // email -> user
const TOKENS: Record<string, { user_id: string; email: string }> = {}; // token -> data

function makeToken(): string {
  return crypto.randomBytes(32).toString('hex');
}

function nowISO(): string {
  return new Date().toISOString();
}

// ─── Auth Handlers ────────────────────────────────────────────────────────────

function handleRegister(req: NextApiRequest, res: NextApiResponse) {
  const { email, password, first_name = '', last_name = '', ...rest } = req.body || {};

  if (!email || !password) {
    return res.status(400).json({ error: 'Email and password required' });
  }

  const normalizedEmail = email.trim().toLowerCase();

  if (USERS[normalizedEmail]) {
    return res.status(409).json({ error: 'An account with this email already exists', code: 'USER_EXISTS' });
  }

  const userId = `usr_${crypto.randomBytes(8).toString('hex')}`;
  USERS[normalizedEmail] = {
    id: userId,
    email: normalizedEmail,
    first_name: first_name || '',
    last_name: last_name || '',
    password,
    role: 'client',
    created_at: nowISO(),
  };

  const accessToken = makeToken();
  const refreshToken = makeToken();
  TOKENS[accessToken] = { user_id: userId, email: normalizedEmail };
  TOKENS[refreshToken] = { user_id: userId, email: normalizedEmail };

  const user = USERS[normalizedEmail];
  return res.status(200).json({
    success: true,
    access_token: accessToken,
    refresh_token: refreshToken,
    token_type: 'bearer',
    expires_in: 86400,
    user_id: userId,
    role: 'client',
    user: {
      id: userId,
      email: normalizedEmail,
      first_name: user.first_name,
      last_name: user.last_name,
    },
  });
}

function handleLogin(req: NextApiRequest, res: NextApiResponse) {
  const { email, password } = req.body || {};

  if (!email || !password) {
    return res.status(400).json({ error: 'Email and password required' });
  }

  const normalizedEmail = email.trim().toLowerCase();
  const user = USERS[normalizedEmail];

  if (!user || user.password !== password) {
    return res.status(401).json({ error: 'Invalid email or password', code: 'INVALID_CREDENTIALS' });
  }

  const accessToken = makeToken();
  const refreshToken = makeToken();
  TOKENS[accessToken] = { user_id: user.id, email: normalizedEmail };
  TOKENS[refreshToken] = { user_id: user.id, email: normalizedEmail };

  return res.status(200).json({
    success: true,
    access_token: accessToken,
    refresh_token: refreshToken,
    token_type: 'bearer',
    expires_in: 86400,
    user_id: user.id,
    role: user.role,
    user: {
      id: user.id,
      email: user.email,
      first_name: user.first_name,
      last_name: user.last_name,
    },
  });
}

function handleMe(req: NextApiRequest, res: NextApiResponse) {
  const authHeader = req.headers.authorization || '';
  if (!authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  const token = authHeader.slice(7);
  const tokenData = TOKENS[token];
  if (!tokenData) {
    return res.status(401).json({ error: 'Invalid or expired token' });
  }
  const user = USERS[tokenData.email];
  if (!user) {
    return res.status(401).json({ error: 'User not found' });
  }
  return res.status(200).json({
    id: user.id,
    email: user.email,
    first_name: user.first_name,
    last_name: user.last_name,
    role: user.role,
    is_active: true,
    is_verified: false,
    sms_consent: false,
    email_consent: true,
    created_at: user.created_at,
  });
}

function handleRefresh(req: NextApiRequest, res: NextApiResponse) {
  const { refresh_token } = req.body || {};
  const tokenData = TOKENS[refresh_token];
  if (!tokenData) {
    return res.status(401).json({ error: 'Invalid refresh token' });
  }
  const newAccessToken = makeToken();
  TOKENS[newAccessToken] = tokenData;
  const user = USERS[tokenData.email];
  return res.status(200).json({
    access_token: newAccessToken,
    refresh_token,
    token_type: 'bearer',
    expires_in: 86400,
    user_id: tokenData.user_id,
    role: user?.role || 'client',
  });
}

function handleLogout(req: NextApiRequest, res: NextApiResponse) {
  const authHeader = req.headers.authorization || '';
  if (authHeader.startsWith('Bearer ')) {
    delete TOKENS[authHeader.slice(7)];
  }
  return res.status(200).json({ success: true });
}

// ─── Main Handler ─────────────────────────────────────────────────────────────

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  const { path } = req.query;
  const pathStr = Array.isArray(path) ? path.join('/') : typeof path === 'string' ? path : '';

  if (!pathStr) {
    return res.status(400).json({ error: 'No path provided' });
  }

  // ── Intercept Auth Routes (handled locally, no Railway dependency) ──────────
  if (pathStr === 'auth/register' && req.method === 'POST') return handleRegister(req, res);
  if (pathStr === 'auth/login' && req.method === 'POST') return handleLogin(req, res);
  if (pathStr === 'auth/me' && req.method === 'GET') return handleMe(req, res);
  if (pathStr === 'auth/refresh' && req.method === 'POST') return handleRefresh(req, res);
  if (pathStr === 'auth/logout' && req.method === 'POST') return handleLogout(req, res);

  // ── Forward all other routes to Railway backend ───────────────────────────
  try {
    const fetchOptions: RequestInit = {
      method: req.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...(req.headers.authorization ? { Authorization: req.headers.authorization as string } : {}),
      },
    };

    if (req.body && (req.method === 'POST' || req.method === 'PUT' || req.method === 'PATCH')) {
      fetchOptions.body = JSON.stringify(req.body);
    }

    const fullUrl = `${API_BASE}/${pathStr}`;
    console.log(`Proxy: ${req.method} ${fullUrl}`);
    const response = await fetch(fullUrl, fetchOptions);

    let data: any;
    try {
      data = await response.json();
    } catch {
      data = { error: 'Empty response from backend' };
    }

    return res.status(response.status).json(data);
  } catch (error: any) {
    console.error('Proxy error:', error);
    return res.status(502).json({ error: 'Backend unavailable', detail: error.message });
  }
}
