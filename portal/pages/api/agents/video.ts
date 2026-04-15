/**
 * POST /api/agents/video
 * Initiate a video call with Tim Shaw.
 *
 * MVP: Returns a mock call_id.
 * Production: Integrate Twilio Video API here.
 *   - Create Twilio Video Room
 *   - Generate Access Token with VideoGrant
 *   - Return token + roomName to client
 */
import type { NextApiRequest, NextApiResponse } from "next";

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
    const callId = `video_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;

    // TODO: Twilio Video integration
    // const AccessToken = require('twilio').jwt.AccessToken;
    // const VideoGrant = AccessToken.VideoGrant;
    // const token = new AccessToken(accountSid, apiKey, apiSecret, { identity: userId });
    // token.addGrant(new VideoGrant({ room: callId }));
    // const roomName = callId;

    return res.status(200).json({
      success: true,
      call_id: callId,
      status: "initiated",
      message: "Connecting video call…",
      // twilio_token: token.toJwt(),   // uncomment when Twilio is wired
      // room_name: roomName,
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return res.status(500).json({ success: false, error: message });
  }
}
