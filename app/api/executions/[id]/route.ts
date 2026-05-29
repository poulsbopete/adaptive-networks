import { NextResponse } from "next/server";
import { executionDeepLink, getWorkflowExecution } from "@/lib/elastic";

export async function GET(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const detail = await getWorkflowExecution(params.id);
    return NextResponse.json({
      id: detail.id,
      workflowId: detail.workflowId,
      status: detail.status,
      startedAt: detail.startedAt,
      finishedAt: detail.finishedAt,
      currentNodeId: detail.currentNodeId,
      error: detail.error,
      workflowName: detail.workflowDefinition?.name,
      stepExecutions: detail.stepExecutions ?? [],
      kibanaUrl: executionDeepLink(detail.id, detail.workflowId),
      waitingForHuman:
        detail.status === "running" &&
        (detail.currentNodeId?.includes("hitl") ||
          detail.stepExecutions?.some(
            (s) => s.stepId === "hitl_approval" && s.status !== "completed"
          )),
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Execution not found" },
      { status: 500 }
    );
  }
}
