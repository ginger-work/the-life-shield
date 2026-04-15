import type { NextApiRequest, NextApiResponse } from 'next';
import { USERS, TOKENS, makeToken } from '../../../lib/auth-store';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { email, password } = req.body || {};

  if (!email || !password) {
    return res.status(400).json({ error: 'Email and password required' });
  }

  const emailLower = email.trim().toLowerCase();
  const user = USERS[emailLower];

  if (!user || user.password !== password) {
    return res.status(401).json({ error: 'Invalid email or password', code: 'INVALID_CREDENTIALS' });
  }

  const accessToken = makeToken();
  const refreshToken = makeToken();
  TOKENS[accessToken] = { user_id: user.id, email: emailLower };
  TOKENS[refreshToken] = { user_id: user.id, email: emailLower };

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
