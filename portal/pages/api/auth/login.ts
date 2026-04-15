import type { NextApiRequest, NextApiResponse } from 'next';

// Shared in-memory user store (simple MVP solution)
// In production, this would be in a database
const users: Record<string, any> = {
  // Pre-populate with test account for demo
  'deon.work.00000@lifeshield.com': {
    id: 'user_18',
    email: 'deon.work.00000@lifeshield.com',
    password: 'LifeShield2025',
    first_name: 'Deon',
    last_name: 'Robinson',
    email_consent: true,
    created_at: new Date().toISOString(),
  },
};

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({ error: 'Email and password required' });
    }

    const emailLower = email.toLowerCase();
    const user = users[emailLower];

    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    if (user.password !== password) {
      return res.status(401).json({ error: 'Invalid password' });
    }

    const token = `token_${Math.random().toString(36).substring(7)}`;

    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    return res.status(200).json({
      success: true,
      user: {
        id: user.id,
        email: user.email,
        first_name: user.first_name,
        last_name: user.last_name,
      },
      access_token: token,
      refresh_token: `refresh_${Math.random().toString(36).substring(7)}`,
      token_type: 'bearer',
      user_id: user.id,
      role: 'client',
    });
  } catch (error: any) {
    console.error('Login error:', error);
    return res.status(500).json({ error: error.message || 'Login failed' });
  }
}
