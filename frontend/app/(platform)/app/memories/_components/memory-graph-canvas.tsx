'use client'

import { useEffect, useRef, useState, useMemo, useCallback } from 'react'
import * as d3 from 'd3-force'
import { select } from 'd3-selection'
import { zoom as d3Zoom, zoomIdentity } from 'd3-zoom'
import { drag as d3Drag } from 'd3-drag'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'

import type { MemoryEntity, MemoryRelation } from '@/lib/api/memories'
import { memoriesApi } from '@/lib/api/memories'
import { EmptyState } from './empty-state'
import { GraphToolbar } from './graph-toolbar'
import { GraphFilters } from './graph-filters'
import { EntityDetailSheet } from './entity-detail-sheet'

interface Node extends d3.SimulationNodeDatum {
  id: string
  entity: MemoryEntity
  x?: number
  y?: number
  fx?: number | null
  fy?: number | null
}

interface Link extends d3.SimulationLinkDatum<Node> {
  id: string
  relation: MemoryRelation
  source: Node | string
  target: Node | string
}

export function MemoryGraphCanvas() {
  const t = useTranslations('memories')
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const zoomBehaviorRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null)

  const [entities, setEntities] = useState<MemoryEntity[]>([])
  const [relations, setRelations] = useState<MemoryRelation[]>([])
  const [selectedEntity, setSelectedEntity] = useState<MemoryEntity | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [entityTypeFilter, setEntityTypeFilter] = useState<string[]>([])
  const [relationTypeFilter, setRelationTypeFilter] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [filtersInitialized, setFiltersInitialized] = useState(false)

  // Get available types from actual data
  const availableEntityTypes = useMemo(() => {
    return Array.from(new Set(entities.map((e) => e.entity_type)))
  }, [entities])

  const availableRelationTypes = useMemo(() => {
    return Array.from(new Set(relations.map((r) => r.relation_type)))
  }, [relations])

  // Initialize filters with all available types when data loads (only once)
  useEffect(() => {
    if (!filtersInitialized && availableEntityTypes.length > 0) {
      setEntityTypeFilter(availableEntityTypes)
      setRelationTypeFilter(availableRelationTypes)
      setFiltersInitialized(true)
    }
  }, [availableEntityTypes, availableRelationTypes, filtersInitialized])

  // Fetch data
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)
        const data = await memoriesApi.getGraph()
        setEntities(data.entities)
        setRelations(data.relations)
      } catch (error) {
        toast.error(t('fetchError'))
        console.error('Failed to fetch memory graph:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [t])

  // Filter entities and relations
  const filteredEntities = useMemo(() => {
    return entities.filter((entity) => {
      const matchesSearch = searchQuery
        ? entity.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          entity.description?.toLowerCase().includes(searchQuery.toLowerCase())
        : true

      const matchesType = entityTypeFilter.includes(entity.entity_type)

      return matchesSearch && matchesType
    })
  }, [entities, searchQuery, entityTypeFilter])

  const filteredRelations = useMemo(() => {
    const entityIds = new Set(filteredEntities.map((e) => e.id))
    return relations.filter((relation) => {
      const matchesEntities =
        entityIds.has(relation.source_entity_id) &&
        entityIds.has(relation.target_entity_id)

      const matchesType = relationTypeFilter.includes(relation.relation_type)

      return matchesEntities && matchesType
    })
  }, [relations, filteredEntities, relationTypeFilter])

  // Convert to d3 nodes and links
  const { nodes, links } = useMemo(() => {
    const nodes: Node[] = filteredEntities.map((entity) => ({
      id: entity.id,
      entity,
    }))

    const nodeMap = new Map(nodes.map((n) => [n.id, n]))

    const links: Link[] = filteredRelations
      .map((relation): Link | null => {
        const source = nodeMap.get(relation.source_entity_id)
        const target = nodeMap.get(relation.target_entity_id)
        if (!source || !target) return null
        return {
          id: relation.id,
          relation,
          source,
          target,
        }
      })
      .filter((link): link is Link => link !== null)

    return { nodes, links }
  }, [filteredEntities, filteredRelations])

  // Entity type colors
  const getEntityColor = (entityType: string) => {
    const colors: Record<string, string> = {
      person: '#3b82f6',
      preference: '#a855f7',
      skill: '#22c55e',
      project: '#f97316',
      goal: '#eab308',
      fact: '#06b6d4',
      concept: '#ec4899',
      organization: '#6366f1',
      location: '#14b8a6',
      custom: '#6b7280',
    }
    return colors[entityType] || colors.custom
  }

  // Relation type colors
  const getRelationColor = (relationType: string) => {
    const colors: Record<string, string> = {
      prefers: '#a855f7',
      works_on: '#f97316',
      knows: '#3b82f6',
      uses: '#22c55e',
      works_at: '#6366f1',
      located_in: '#14b8a6',
      has_goal: '#eab308',
      related_to: '#ec4899',
      part_of: '#06b6d4',
    }
    return colors[relationType] || '#999'
  }

  // D3 force simulation
  useEffect(() => {
    if (!svgRef.current || !containerRef.current) return

    const svg = select(svgRef.current)
    const container = containerRef.current
    const width = container.clientWidth
    const height = container.clientHeight

    // Clear previous content
    svg.selectAll('*').remove()

    // If no nodes, just return after clearing
    if (nodes.length === 0) return

    // Create zoom behavior
    const zoomBehavior = d3Zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform)
      })

    // Store zoom behavior in ref for button controls
    zoomBehaviorRef.current = zoomBehavior
    svg.call(zoomBehavior)

    // Create main group
    const g = svg.append('g')

    // Create simulation with radial layout
    const simulation = d3
      .forceSimulation<Node>(nodes)
      .force(
        'link',
        d3
          .forceLink<Node, Link>(links)
          .id((d) => d.id)
          .distance(100)
      )
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(50))

    // Create links
    const link = g
      .append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', (d) => getRelationColor(d.relation.relation_type))
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 2)

    // Create link labels
    const linkLabel = g
      .append('g')
      .selectAll('text')
      .data(links)
      .join('text')
      .attr('font-size', 10)
      .attr('fill', '#666')
      .attr('text-anchor', 'middle')
      .text((d) => t(`relationTypes.${d.relation.relation_type}`))

    // Create nodes
    const node = g
      .append('g')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .call(
        d3Drag<SVGGElement, Node>()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart()
            d.fx = d.x
            d.fy = d.y
          })
          .on('drag', (event, d) => {
            d.fx = event.x
            d.fy = event.y
          })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0)
            d.fx = null
            d.fy = null
          }) as never
      )
      .on('click', (_, d) => {
        setSelectedEntity(d.entity)
      })

    // Add circles to nodes
    node
      .append('circle')
      .attr('r', 30)
      .attr('fill', (d) => getEntityColor(d.entity.entity_type))
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .style('cursor', 'pointer')

    // Add labels to nodes
    node
      .append('text')
      .attr('dy', 4)
      .attr('text-anchor', 'middle')
      .attr('font-size', 12)
      .attr('fill', '#fff')
      .attr('pointer-events', 'none')
      .text((d) => {
        const name = d.entity.name
        return name.length > 10 ? name.substring(0, 10) + '...' : name
      })

    // Add title for hover
    node.append('title').text((d) => d.entity.name)

    // Update positions on tick
    simulation.on('tick', () => {
      link
        .attr('x1', (d) => (d.source as Node).x || 0)
        .attr('y1', (d) => (d.source as Node).y || 0)
        .attr('x2', (d) => (d.target as Node).x || 0)
        .attr('y2', (d) => (d.target as Node).y || 0)

      linkLabel
        .attr('x', (d) => ((d.source as Node).x! + (d.target as Node).x!) / 2)
        .attr('y', (d) => ((d.source as Node).y! + (d.target as Node).y!) / 2)

      node.attr('transform', (d) => `translate(${d.x},${d.y})`)
    })

    // Cleanup
    return () => {
      simulation.stop()
    }
  }, [nodes, links, t])

  // Zoom controls
  const handleZoomIn = useCallback(() => {
    if (!svgRef.current || !zoomBehaviorRef.current) return
    const svg = select(svgRef.current)
    svg.transition().duration(300).call(zoomBehaviorRef.current.scaleBy, 1.3)
  }, [])

  const handleZoomOut = useCallback(() => {
    if (!svgRef.current || !zoomBehaviorRef.current) return
    const svg = select(svgRef.current)
    svg.transition().duration(300).call(zoomBehaviorRef.current.scaleBy, 0.7)
  }, [])

  const handleFitView = useCallback(() => {
    if (!svgRef.current || !containerRef.current || !zoomBehaviorRef.current) return
    const svg = select(svgRef.current)
    const container = containerRef.current
    const width = container.clientWidth
    const height = container.clientHeight

    // Reset to identity transform (no translation, scale 1)
    svg
      .transition()
      .duration(300)
      .call(
        zoomBehaviorRef.current.transform,
        zoomIdentity
      )
  }, [])

  const handleNavigateToEntity = useCallback(
    (entityId: string) => {
      const entity = entities.find((e) => e.id === entityId)
      if (entity) {
        setSelectedEntity(entity)
      }
    },
    [entities]
  )

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    )
  }

  if (entities.length === 0) {
    return <EmptyState />
  }

  return (
    <div className="relative h-full w-full" ref={containerRef}>
      <svg ref={svgRef} className="w-full h-full" />

      {/* Toolbar */}
      <div className="absolute top-4 left-4 z-10">
        <GraphToolbar
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onZoomIn={handleZoomIn}
          onZoomOut={handleZoomOut}
          onFitView={handleFitView}
          entityCount={filteredEntities.length}
          relationCount={filteredRelations.length}
        />
      </div>

      {/* Filters */}
      <div className="absolute top-4 right-4 z-10">
        <GraphFilters
          availableEntityTypes={availableEntityTypes}
          availableRelationTypes={availableRelationTypes}
          entityTypeFilter={entityTypeFilter}
          onEntityTypeFilterChange={setEntityTypeFilter}
          relationTypeFilter={relationTypeFilter}
          onRelationTypeFilterChange={setRelationTypeFilter}
        />
      </div>

      {/* Entity Detail Sheet */}
      <EntityDetailSheet
        entity={selectedEntity}
        entities={entities}
        relations={relations}
        onClose={() => setSelectedEntity(null)}
        onNavigateToEntity={handleNavigateToEntity}
      />
    </div>
  )
}
