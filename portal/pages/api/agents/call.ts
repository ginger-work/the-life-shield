/**
 * POST /api/agents/call
 * Initiate a voice call with Tim Shaw.
 *
 * MVP: Returns a mock call_id.
 * Production: Integrate Twilio Voice API here.
 *   - Create TwiML App / Twilio Voice token
 *   - Store call record in DB
 *   - Return Twilio capability token to client
 */
import type { NextApiRequest, NextApiResponse } from "next";

// In-memory store for MVP — replace with DB in production
const activeCalls: Record<string, { type: string; startedAt: string; status: string }> = {};

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method === "OPTIONS") {
    res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");
    return res.status(204).end();
  }

  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  try {
    const callId = `call_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    const startedAt = new Date().toISOString();

    // Store call record (MVP in-memory)
    activeCalls[callId] = { type: "voice", startedAt, status: "initiated" };

    // TODO: Twilio Voice integration
    // const twilio = require('twilio')(process.env.TWILIO_ACCOUNT_SID, process.env.TWILIO_AUTH_TOKEN);
    // const call = await twilio.calls.create({ ... });

    return res.status(200).json({
      success: true,
      call_id: callId,
      status: "initiated",
      message: "Connecting you to Tim Shaw…",
      // twilio_token: "<capability_token>",  // uncomment when Twilio is wired
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return res.status(500).json({ success: false, error: message });
  }
}
