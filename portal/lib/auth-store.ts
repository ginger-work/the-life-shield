/**
 * Shared in-memory auth store for Vercel API routes.
 *
 * Because each Vercel serverless function can be a separate execution context,
 * this module is imported by BOTH register.ts and login.ts so they share the
 * same USERS map within the same function instance.
 *
 * NOTE: In-memory state resets on cold-starts / redeploys. For persistence,
 * replace with Supabase / PlanetScale / Upstash Redis.
 */

import * as crypto from 'crypto';

export interface User {
  id: string;
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  role: string;
  email_consent: boolean;
  created_at: string;
}

// Shared maps — module-level state persists across requests in same instance
export const USERS: Record<string, User> = {};
export const TOKENS: Record<string, { user_id: string; email: string }> = {};

export function makeToken(): string {
  return crypto.randomBytes(32).toString('hex');
}

export function nowISO(): string {
  return new Date().toISOString();
}

export function makeUserId(): string {
  return `usr_${crypto.randomBytes(8).toString('hex')}`;
}
