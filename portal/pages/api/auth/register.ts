import type { NextApiRequest, NextApiResponse } from 'next';

// In-memory user store (for MVP, lost on restart)
const users: Record<string, any> = {};

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { email, password, first_name, last_name, email_consent } = req.body;

    if (!email || !password) {
      return res.status(400).json({ error: 'Email and password required' });
    }

    const emailLower = email.toLowerCase();

    if (users[emailLower]) {
      return res.status(400).json({ error: 'User exists' });
    }

    const userId = `user_${Date.now()}`;
    const token = `token_${Math.random().toString(36).substring(7)}`;

    users[emailLower] = {
      id: userId,
      email: emailLower,
      password,
      first_name,
      last_name,
      email_consent,
      created_at: new Date().toISOString(),
    };

    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    return res.status(200).json({
      success: true,
      user: {
        id: userId,
        email: emailLower,
        first_name,
        last_name,
      },
      access_token: token,
      token_type: 'bearer',
    });
  } catch (error: any) {
    console.error('Registration error:', error);
    return res.status(500).json({ error: error.message || 'Registration failed' });
  }
}
