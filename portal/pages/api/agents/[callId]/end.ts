/**
 * POST /api/agents/call/:callId/end
 * End an active call and log details.
 *
 * MVP: Logs call duration to console + returns summary.
 * Production: Update DB record, notify backend, log to CRM.
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

  const { callId } = req.query;
  const { duration, type } = req.body || {};

  try {
    const callIdStr = Array.isArray(callId) ? callId[0] : callId;

    // Log call record (MVP)
    console.log(`[Call End] ID=${callIdStr} | Type=${type || "unknown"} | Duration=${duration || 0}s`);

    // TODO: Production — persist to DB
    // await db.calls.update({ id: callIdStr }, { status: "completed", duration, ended_at: new Date() });

    return res.status(200).json({
      success: true,
      call_id: callIdStr,
      duration: duration || 0,
      logged: true,
      message: "Call ended successfully",
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return res.status(500).json({ success: false, error: message });
  }
}
