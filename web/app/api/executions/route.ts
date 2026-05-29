import { NextResponse } from "next/server";
import {
  executionDeepLink,
  getWorkflowExecution,
  listWorkflowExecutions,
  resolveIncidentWorkflowId,
} from "@/lib/elastic";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const since = searchParams.get("since");
    const workflowId = searchParams.get("workflowId") || (await resolveIncidentWorkflowId());

    const list = await listWorkflowExecutions(workflowId, 1, 15);
    let results = list.results ?? [];

    if (since) {
      const sinceMs = Date.parse(since);
      results = results.filter((r) => r.startedAt && Date.parse(r.startedAt) >= sinceMs - 5000);
    }

    const enriched = await Promise.all(
      results.slice(0, 5).map(async (item) => {
        const detail = await getWorkflowExecution(item.id);
        return {
          id: detail.id,
          workflowId: detail.workflowId,
          status: detail.status,
          startedAt: detail.startedAt,
          finishedAt: detail.finishedAt,
          currentNodeId: detail.currentNodeId,
          workflowName: detail.workflowDefinition?.name,
          stepExecutions: (detail.stepExecutions ?? []).map((s) => ({
            stepId: s.stepId,
            stepType: s.stepType,
            status: s.status,
            executionTimeMs: s.executionTimeMs,
          })),
          kibanaUrl: executionDeepLink(detail.id, detail.workflowId),
          waitingForHuman:
            detail.status === "running" &&
            (detail.currentNodeId?.includes("hitl") ||
              detail.stepExecutions?.some(
                (s) => s.stepId === "hitl_approval" && s.status !== "completed"
              )),
        };
      })
    );

    return NextResponse.json({
      workflowId,
      total: list.total,
      executions: enriched,
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to list executions" },
      { status: 500 }
    );
  }
}
