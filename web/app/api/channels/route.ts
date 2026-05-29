import { NextResponse } from "next/server";
import { FAULT_CHANNELS } from "@/lib/channels";

export async function GET() {
  return NextResponse.json({ channels: FAULT_CHANNELS });
}
