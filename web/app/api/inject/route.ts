import { NextResponse } from "next/server";
import { assertDemoAuth } from "@/lib/elastic";
import { injectFaultLogs } from "@/lib/otlp";

export async function POST(request: Request) {
  try {
    assertDemoAuth(request);
    const body = (await request.json()) as { channel?: number };
    const channel = Number(body.channel);
    if (![1, 2, 3, 4].includes(channel)) {
      return NextResponse.json({ error: "channel must be 1-4" }, { status: 400 });
    }

    const result = await injectFaultLogs(channel);
    const injectedAt = new Date().toISOString();

    return NextResponse.json({
      ok: true,
      channel: result.channel,
      errorType: result.errorType,
      logsSent: result.logsSent,
      injectedAt,
      message:
        "Fault logs sent to otel-demo. Kibana alert rules evaluate every ~60s, then the Network Incident Response workflow runs.",
    });
  } catch (error) {
    const status = error instanceof Error && error.message === "Unauthorized" ? 401 : 500;
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Inject failed" },
      { status }
    );
  }
}
