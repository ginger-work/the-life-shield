import type { NextApiRequest, NextApiResponse } from 'next';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  const { path } = req.query;
  const pathStr = Array.isArray(path) ? path.join('/') : typeof path === 'string' ? path : '';
  
  if (!pathStr) {
    return res.status(400).json({ error: 'No path provided' });
  }
  
  try {
    const fetchOptions: RequestInit = {
      method: req.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    };
    
    if (req.body && (req.method === 'POST' || req.method === 'PUT')) {
      fetchOptions.body = JSON.stringify(req.body);
    }
    
    const fullUrl = `${API_BASE}/${pathStr}`;
    console.log(`Proxy: ${req.method} ${fullUrl}`);
    const response = await fetch(fullUrl, fetchOptions);
    const data = await response.json();
    
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    
    return res.status(response.status).json(data);
  } catch (error: any) {
    return res.status(500).json({ error: error.message || 'Proxy error' });
  }
}
