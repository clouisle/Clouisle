export interface DecisionBranchConfig {
  questionType?: "choice" | "score" | "noul";
  options?: string[];
  defaultHandle?: string;
}

type BranchEdge = {
  source: string;
  sourceHandle?: string | null;
};

export function getDecisionOutputHandles(
  config: DecisionBranchConfig = {},
): string[] {
  const questionType = config.questionType ?? "choice";
  const branchHandles =
    questionType === "choice" || questionType === "score"
      ? (config.options ?? ["yes", "no"])
      : ["yes", "no"];
  return [...new Set([...branchHandles, config.defaultHandle || "default"])];
}

export function migrateLegacyDecisionBranchEdges<T extends BranchEdge>(
  nodes: Array<{
    id: string;
    type?: string;
    data?: {
      type?: string;
      decisionConfig?: DecisionBranchConfig;
    };
  }>,
  edges: T[],
): T[] {
  let migratedEdges = edges;
  for (const node of nodes) {
    if ((node.type || node.data?.type) !== "decision") continue;
    const config = node.data?.decisionConfig || {};
    const questionType = config.questionType ?? "choice";
    if (questionType !== "choice" && questionType !== "score") continue;
    const options = config.options ?? ["yes", "no"];
    if (
      options.length !== 2 ||
      options.some((option) => !option.trim()) ||
      new Set(options).size !== 2 ||
      options.includes("yes") ||
      options.includes("no") ||
      ["yes", "no"].includes(config.defaultHandle || "default")
    ) {
      continue;
    }
    const [yesOption, noOption] = options;

    const remapped = new Map<string, string>([
      ["yes", yesOption],
      ["no", noOption],
    ]);
    const validHandles = new Set(getDecisionOutputHandles(config));
    let changed = false;
    const remappedEdges = migratedEdges.map((edge) => {
      if (
        edge.source !== node.id ||
        !edge.sourceHandle ||
        validHandles.has(edge.sourceHandle)
      ) {
        return edge;
      }
      const nextHandle = remapped.get(edge.sourceHandle);
      if (!nextHandle) return edge;
      changed = true;
      return { ...edge, sourceHandle: nextHandle };
    });
    if (changed) migratedEdges = remappedEdges;
  }
  return migratedEdges;
}

export function remapDecisionBranchEdges<T extends BranchEdge>(
  edges: T[],
  nodeId: string,
  previousConfig: DecisionBranchConfig,
  nextConfig: DecisionBranchConfig,
): T[] {
  const previousQuestionType = previousConfig.questionType ?? "choice";
  const nextQuestionType = nextConfig.questionType ?? "choice";
  const previousHandles =
    previousQuestionType === "choice" || previousQuestionType === "score"
      ? (previousConfig.options ?? ["yes", "no"])
      : ["yes", "no"];
  const nextHandles =
    nextQuestionType === "choice" || nextQuestionType === "score"
      ? (nextConfig.options ?? ["yes", "no"])
      : ["yes", "no"];
  const nextHandleSet = new Set(nextHandles);
  const handleMap = new Map<string, string>();

  for (const handle of previousHandles) {
    if (nextHandleSet.has(handle)) handleMap.set(handle, handle);
  }

  if (previousHandles.length === nextHandles.length) {
    const mappedTargets = new Set(handleMap.values());
    for (const [index, previousHandle] of previousHandles.entries()) {
      const nextHandle = nextHandles[index];
      if (
        !handleMap.has(previousHandle) &&
        !nextHandleSet.has(previousHandle) &&
        !mappedTargets.has(nextHandle)
      ) {
        handleMap.set(previousHandle, nextHandle);
        mappedTargets.add(nextHandle);
      }
    }
  }

  const previousFallback = previousConfig.defaultHandle || "default";
  const nextFallback = nextConfig.defaultHandle || "default";
  if (
    previousFallback !== nextFallback &&
    !previousHandles.includes(previousFallback)
  ) {
    handleMap.set(previousFallback, nextFallback);
  }

  let changed = false;
  const remapped = edges.map((edge) => {
    if (edge.source !== nodeId || !edge.sourceHandle) return edge;
    const nextHandle = handleMap.get(edge.sourceHandle);
    if (!nextHandle || nextHandle === edge.sourceHandle) return edge;
    changed = true;
    return { ...edge, sourceHandle: nextHandle };
  });

  return changed ? remapped : edges;
}
