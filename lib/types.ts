export interface StepExecution {
  id: string;
  stepId: string;
  stepType: string;
  status: string;
  startedAt?: string;
  finishedAt?: string;
  executionTimeMs?: number;
  error?: { message?: string };
}

export interface WorkflowExecution {
  id: string;
  workflowId: string;
  status: string;
  startedAt?: string;
  finishedAt?: string;
  currentNodeId?: string;
  error?: { message?: string } | string | null;
  stepExecutions?: StepExecution[];
  workflowDefinition?: { name?: string };
}

export interface InjectResult {
  ok: boolean;
  channel: number;
  errorType: string;
  logsSent: number;
  injectedAt: string;
  message: string;
}

export interface DemoConfig {
  kibanaUrl: string;
  workflowName: string;
  workflowId: string | null;
  alertIntervalHint: string;
}
