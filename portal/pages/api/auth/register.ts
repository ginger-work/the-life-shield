import type { NextApiRequest, NextApiResponse } from 'next';
import { USERS, TOKENS, makeToken, makeUserId, nowISO } from '../../../lib/auth-store';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { email, password, first_name = '', last_name = '', email_consent = true } = req.body || {};

  if (!email || !password) {
    return res.status(400).json({ error: 'Email and password required' });
  }

  const emailLower = email.trim().toLowerCase();

  if (USERS[emailLower]) {
    return res.status(409).json({ error: 'An account with this email already exists', code: 'USER_EXISTS' });
  }

  const userId = makeUserId();
  USERS[emailLower] = {
    id: userId,
    email: emailLower,
    password,
    first_name,
    last_name,
    role: 'client',
    email_consent,
    created_at: nowISO(),
  };

  const accessToken = makeToken();
  const refreshToken = makeToken();
  TOKENS[accessToken] = { user_id: userId, email: emailLower };
  TOKENS[refreshToken] = { user_id: userId, email: emailLower };

  const user = USERS[emailLower];
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
      email: emailLower,
      first_name: user.first_name,
      last_name: user.last_name,
    },
  });
}
