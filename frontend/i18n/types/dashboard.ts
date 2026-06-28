// GENERATED — 2026-06-27T18:55:50.876Z
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
      tabs: {
        overview: string
        health: string
        agents: string
        workflows: string
        timeouts: string
        throughput: string
        tokens: string
        workers: string
        "slow-queries": string
      }
      actions: {
        refresh: string
        retry: string
        viewDetails: string
        closeDetails: string
      }
      states: {
        loading: string
        refreshing: string
        emptyTitle: string
        emptyDescription: string
        errorTitle: string
        errorDescription: string
        lastUpdated: string
        cacheTtl: string
        autoRefreshHint: string
      }
      status: {
        healthy: string
        warning: string
        danger: string
        unhealthy: string
        unknown: string
        success: string
        failed: string
        running: string
        pending: string
        cancelled: string
        timeout: string
        error: string
      }
      sources: {
        agent: string
        workflow: string
        system: string
        unknown: string
      }
      risk: {
        healthy: string
        warning: string
        critical: string
      }
      metrics: {
        totalRequests: string
        agentWorkflowBreakdown: string
        p95Latency: string
        p95Ttft: string
        firstTokenLatency: string
        timeoutRate: string
        successRate: string
        successRateValue: string
        currentQps: string
        currentTps: string
        peakHourly: string
        totalTokens: string
        selectedRange: string
      }
      alerts: {
        reliability: string
        latency: string
        ttft: string
        load: string
        latencyHint: string
        ttftHint: string
        loadHint: string
      }
      overview: {
        operationalStatus: string
        operationalStatusDesc: string
        trafficMix: string
        latencyPercentiles: string
        requestsBySource: string
        agentRequests: string
        workflowRuns: string
        healthSummaryHealthy: string
        healthSummaryWarning: string
        healthSummaryCritical: string
      }
      charts: {
        requestTrend: string
        requestTrendDesc: string
        systemTrend: string
        systemTrendDesc: string
        throughputTrend: string
        throughputTrendDesc: string
      }
      health: {
        memory: string
        disk: string
        database: string
        resourceUsage: string
        dependencies: string
        workerQueues: string
        workerQueuesDesc: string
        activeTasks: string
        reservedTasks: string
        scheduledTasks: string
        pending: string
        queue: string
        slowQueries: string
        slowQueriesDesc: string
        query: string
        calls: string
        meanTime: string
        totalTime: string
        workerError: string
        noSlowQueries: string
        slowQueriesUnavailable: string
        slowQueriesSetupHint: string
        reason: string
        actions: {
          cpuAction: string
          memoryAction: string
          diskAction: string
          databaseAction: string
          redisAction: string
          workerAction: string
        }
      }
      tables: {
        name: string
        team: string
        requests: string
        runs: string
        errors: string
        timeouts: string
        successRate: string
        timeoutRate: string
        ttftP95: string
        tokens: string
        avgTokens: string
        failedNodes: string
        source: string
        type: string
        status: string
        model: string
        duration: string
        time: string
      }
      details: {
        agentTitle: string
        workflowTitle: string
        id: string
        team: string
        performanceTrend: string
        percentiles: string
        nodeBreakdown: string
        noAgent: string
        noWorkflow: string
        failedRate: string
        avgTokens: string
        avgNodes: string
        nodeType: string
        executionCount: string
        failedCount: string
        avgDuration: string
      }
      common: {
        count: string
      }
      timeouts: {
        limitedTitle: string
        limitedDescription: string
        distribution: string
        distributionDesc: string
        recentEvents: string
        totalEvents: string
        mostFrequentType: string
        typeAvailable: string
        note: string
      }
      timeoutTypes: {
        unknown: string
        idle: string
        global: string
        workflow: string
        agent: string
      }
      throughput: {
        currentLoad: string
        runningWorkflows: string
        requestVolume: string
        tokenBySource: string
        tokenByModel: string
        model: string
        tokens: string
        share: string
        noTokenData: string
      }
      tokens: {
        costDriver: string
        topModel: string
        modelCount: string
        sourceDesc: string
        modelDesc: string
      }
      workers: {
        count: string
        inFlight: string
        pendingQueues: string
        queueDesc: string
      }
      slowQueries: {
        threshold: string
        thresholdDesc: string
        topMeanTime: string
        setupDesc: string
        setupSteps: string
      }
    }
  }
}
