// GENERATED — 2026-10-08T18:56:50.219Z
// Source: i18n/en/dashboard.json
export type DashboardMessages = {
  dashboard: {
    common: {
      loading: string
      noData: string
      unknown: string
      count: string
      percentage: string
      usageCount: string
      tokenUsage: string
      conversations: string
      messages: string
      team: string
      runCount: string
    }
    status: {
      success: string
      failed: string
      running: string
      pending: string
    }
    triggers: {
      manual: string
      scheduled: string
      webhook: string
      api: string
    }
    tabs: {
      overview: string
      models: string
      analytics: string
    }
    timeRange: {
      "7d": string
      "30d": string
      "90d": string
      all: string
      custom: string
    }
    actions: {
      refresh: string
      export: string
      autoRefresh: string
    }
    charts: {
      topAgents: string
      topAgentsDesc: string
      teamTokenUsage: string
      teamTokenUsageDesc: string
      modelDistribution: string
      modelDistributionDesc: string
      conversationHeatmap: string
      conversationHeatmapDesc: string
      workflowStats: string
      workflowStatsDesc: string
      workflowSuccessRate: string
      costAnalysis: string
      quotaUsage: string
      realtimeActivity: string
    }
    metrics: {
      totalUsers: string
      dau: string
      totalConversations: string
      totalTokens: string
      estimatedCost: string
      successRate: string
      avgResponseTime: string
      totalRuns: string
      avgDuration: string
      conversationCount: string
      messageCount: string
      tokenUsage: string
    }
    models: {
      totalTokens: string
      avgTokensPerMessage: string
      mostUsedModel: string
      totalMessages: string
      tokenTrend: string
      tokenTrendDesc: string
      teamRanking: string
      teamRankingDesc: string
      modelDetails: string
      deletedModel: string
      topAgentsByTokens: string
    }
    analytics: {
      workflowRuns: string
      successRate: string
      avgDuration: string
      topAgent: string
      workflowStatus: string
      workflowStatusDesc: string
      workflowTriggers: string
      workflowTriggersDesc: string
      topWorkflows: string
      topWorkflowsDesc: string
      agentPerformance: string
      agentPerformanceDesc: string
      metricSelector: string
    }
    home: {
      title: string
      description: string
      userGrowth: string
      userGrowthDesc: string
      activityTrend: string
      activityTrendDesc: string
      resources: string
      resourcesDesc: string
      systemStats: string
      systemStatsDesc: string
      stats: {
        totalUsers: string
        totalTeams: string
        totalAgents: string
        totalWorkflows: string
        totalKnowledgeBases: string
        totalConversations: string
        totalMessages: string
        totalTokens: string
        dau: string
        dauDesc: string
        wau: string
        wauDesc: string
        mau: string
        mauDesc: string
        newUsers: string
        activeUsers: string
        conversations: string
        tokens: string
        teams: string
        teamsDesc: string
        agents: string
        agentsDesc: string
        workflows: string
        workflowsDesc: string
        knowledgeBases: string
        knowledgeBasesDesc: string
        avgMessagesPerConv: string
        avgTokensPerMessage: string
        twoFactorAuth: string
        users: string
        adoptionRate: string
      }
      passwordExpiration: {
        title: string
        description: string
        expired: string
        expiredDesc: string
        expiringSoon: string
        expiringSoonDesc: string
        forceChange: string
        forceChangeDesc: string
        allGood: string
      }
    }
    observability: {
      title: string
      description: string
      consoleDescription: string
      tabs: {
        overview: string
        runs: string
        dependencies: string
        queues: string
        infrastructure: string
        alerts: string
      }
      actions: {
        refresh: string
        retry: string
        apply: string
        openIssue: string
        loadMore: string
        save: string
      }
      filters: {
        team: string
        teamId: string
        period: string
        source: string
        allSources: string
        status: string
        allStatuses: string
        errorCategory: string
        runId: string
        alertStatus: string
      }
      periods: {
        "15m": string
        "1h": string
        "24h": string
        "7d": string
      }
      states: {
        loading: string
        errorDescription: string
        lastUpdated: string
        noSamples: string
        unavailableDetail: string
      }
      quality: {
        fresh: string
        partial: string
        stale: string
        unavailable: string
        no_data: string
        window: string
        lastSample: string
      }
      status: {
        healthy: string
        warning: string
        danger: string
        unhealthy: string
        unknown: string
        success: string
        completed: string
        completing: string
        failed: string
        interrupted: string
        running: string
        stopping: string
        stopped: string
        waiting: string
        pending: string
        queued: string
        cancelled: string
        timeout: string
        error: string
        degraded: string
        unavailable: string
        stale: string
        offline: string
      }
      sources: {
        agent: string
        workflow: string
      }
      severity: {
        critical: string
        warning: string
        info: string
      }
      issues: {
        affected: string
        none: string
      }
      metrics: {
        agentSubmitted: string
        agentSuccessRate: string
        agentP95: string
        firstTokenP95: string
        agentTokens: string
        workflowSubmitted: string
        workflowSuccessRate: string
        workflowP95: string
        workflowTokens: string
        completedFailed: string
      }
      charts: {
        runTrend: string
        runTrendDesc: string
        completed: string
        failed: string
        submitted: string
        latencyTrend: string
        latencyTrendDesc: string
        p95: string
        firstTokenP95: string
        tokenTrend: string
        tokenTrendDesc: string
        tokens: string
        sampleCoverage: string
      }
      runs: {
        title: string
        description: string
        columns: {
          source: string
          name: string
          team: string
          status: string
          submitted: string
          queue: string
          duration: string
          tokens: string
          error: string
          trace: string
        }
      }
      dependencies: {
        models: string
        tools: string
        retrieval: string
        description: string
        requests: string
        samples: string
        successRate: string
        completedFailed: string
        p50: string
        p95: string
        firstTokenP95: string
        tokens: string
      }
      queues: {
        workers: string
        workersDescription: string
        workerQueues: string
        lastHeartbeat: string
        scheduled: string
        queues: string
        queuesDescription: string
        active: string
        reserved: string
        pending: string
        consumers: string
        oldestWait: string
        observedAt: string
        pendingTrend: string
      }
      infrastructure: {
        instances: string
        dependencies: string
        latency: string
        slowQueries: string
        safeQueryNotice: string
        queryReset: string
        calls: string
        mean: string
        max: string
        total: string
        roles: {
          api: string
        }
        metric: {
          cpu_percent: string
          memory_percent: string
        }
        scope: {
          host: string
        }
        retainedSample: string
        lastObservedAt: string
      }
      alerts: {
        events: string
        eventsDescription: string
        active: string
        resolved: string
        all: string
        acknowledge: string
        silence: string
        silenceDuration: string
        seconds: string
        started: string
        silencedUntil: string
        noEvents: string
        rules: string
        rulesDescription: string
        enabled: string
        threshold: string
        evaluationWindow: string
        recoveryWindow: string
      }
      details: {
        runTitle: string
        traceDescription: string
        traceStatus: string
        complete: string
        incomplete: string
        traceExpired: string
        traceTruncated: string
        waterfall: string
        traceUnavailable: string
        errorCategory: string
      }
    }
  }
}
