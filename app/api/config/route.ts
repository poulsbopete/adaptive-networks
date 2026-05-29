import { NextResponse } from "next/server";
import { getPublicConfig } from "@/lib/elastic";

export async function GET() {
  try {
    return NextResponse.json(getPublicConfig());
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Config unavailable" },
      { status: 500 }
    );
  }
}
