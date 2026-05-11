'use client'

import { useEffect, useRef, useState, useMemo, useCallback } from 'react'
import * as d3 from 'd3-force'
import { select } from 'd3-selection'
import { zoom as d3Zoom, zoomIdentity, zoomTransform, type ZoomBehavior } from 'd3-zoom'
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
  const tCommon = useTranslations('common')
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const zoomBehaviorRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null)

  const getRelationTypeLabel = useCallback((relationType: string) => {
    const key = `relationTypes.${relationType}`
    return t.has(key) ? t(key) : relationType
  }, [t])

  const [entities, setEntities] = useState<MemoryEntity[]>([])
  const [relations, setRelations] = useState<MemoryRelation[]>([])
  const [selectedEntity, setSelectedEntity] = useState<MemoryEntity | null>(null)
  const [selectedEntityIds, setSelectedEntityIds] = useState<Set<string>>(new Set())
  const [selectMode, setSelectMode] = useState(false)
  const selectModeRef = useRef(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [entityTypeFilter, setEntityTypeFilter] = useState<string[]>([])
  const [relationTypeFilter, setRelationTypeFilter] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [filtersInitialized, setFiltersInitialized] = useState(false)

  // Keep ref in sync for D3 click handler
  useEffect(() => {
    selectModeRef.current = selectMode
  }, [selectMode])

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
  const fetchData = useCallback(async () => {
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
  }, [t])

  useEffect(() => {
    fetchData()
  }, [fetchData])

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
        return { id: relation.id, relation, source, target }
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

    svg.selectAll('*').remove()
    if (nodes.length === 0) return

    const zoomBehavior = d3Zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .filter((event) => {
        // Wheel: only zoom with Ctrl/Cmd (includes trackpad pinch)
        if (event.type === 'wheel') {
          return event.ctrlKey || event.metaKey
        }
        // Drag: in select mode, only pan with Ctrl/Cmd
        if (event.type === 'mousedown' || event.type === 'pointerdown') {
          if (selectModeRef.current) {
            return event.ctrlKey || event.metaKey
          }
        }
        return true
      })
      .on('zoom', (event) => {
        g.attr('transform', event.transform)
      })

    zoomBehaviorRef.current = zoomBehavior
    svg.call(zoomBehavior)

    // Plain wheel / trackpad swipe → pan
    const handleWheelPan = (event: WheelEvent) => {
      if (event.ctrlKey || event.metaKey) return
      event.preventDefault()
      const svgEl = svgRef.current!
      const cur = zoomTransform(svgEl)
      const nt = zoomIdentity.translate(cur.x - event.deltaX, cur.y - event.deltaY).scale(cur.k)
      svg.call(zoomBehavior.transform, nt)
    }
    const svgEl = svgRef.current
    svgEl.addEventListener('wheel', handleWheelPan, { passive: false })

    const g = svg.append('g')

    const simulation = d3
      .forceSimulation<Node>(nodes)
      .force(
        'link',
        d3.forceLink<Node, Link>(links).id((d) => d.id).distance(100)
      )
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(50))

    const link = g
      .append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', (d) => getRelationColor(d.relation.relation_type))
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 2)

    const linkLabel = g
      .append('g')
      .selectAll('text')
      .data(links)
      .join('text')
      .attr('font-size', 10)
      .attr('fill', '#666')
      .attr('text-anchor', 'middle')
      .text((d) => getRelationTypeLabel(d.relation.relation_type))

    const node = g
      .append('g')
      .attr('class', 'nodes')
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
        if (selectModeRef.current) {
          // Toggle selection in select mode
          setSelectedEntityIds((prev) => {
            const next = new Set(prev)
            if (next.has(d.id)) {
              next.delete(d.id)
            } else {
              next.add(d.id)
            }
            return next
          })
        } else {
          setSelectedEntity(d.entity)
        }
      })

    node
      .append('circle')
      .attr('r', 30)
      .attr('fill', (d) => getEntityColor(d.entity.entity_type))
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .style('cursor', 'pointer')

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

    node.append('title').text((d) => d.entity.name)

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

    return () => {
      simulation.stop()
      svgEl.removeEventListener('wheel', handleWheelPan)
    }
  }, [nodes, links, t, getRelationTypeLabel])

  // Highlight selected entity node (separate effect to avoid rebuilding simulation)
  useEffect(() => {
    if (!svgRef.current) return
    const svg = select(svgRef.current)
    const selectedId = selectedEntity?.id

    svg.selectAll<SVGGElement, Node>('.nodes g').each(function (d) {
      const circle = select(this).select('circle')
      if (d.id === selectedId) {
        circle
          .attr('r', 40)
          .attr('stroke', '#fbbf24')
          .attr('stroke-width', 3)
      } else {
        circle
          .attr('r', 30)
          .attr('stroke', '#fff')
          .attr('stroke-width', 2)
      }
    })
  }, [selectedEntity])

  // Highlight multi-selected nodes
  useEffect(() => {
    if (!svgRef.current) return
    const svg = select(svgRef.current)

    svg.selectAll<SVGGElement, Node>('.nodes g').each(function (d) {
      const circle = select(this).select('circle')
      // Don't override the single-selected highlight
      if (d.id === selectedEntity?.id) return

      if (selectedEntityIds.has(d.id)) {
        circle
          .attr('stroke', '#fbbf24')
          .attr('stroke-width', 2)
          .attr('stroke-dasharray', '4 2')
      } else {
        circle
          .attr('stroke', '#fff')
          .attr('stroke-width', 2)
          .attr('stroke-dasharray', null)
      }
    })
  }, [selectedEntityIds, selectedEntity])

  // Keyboard shortcuts: Escape to clear selection and exit select mode
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelectedEntityIds(new Set())
        setSelectMode(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Select mode: enable drag-to-select rectangle and click-to-toggle
  useEffect(() => {
    if (!svgRef.current) return
    const svg = select(svgRef.current)

    if (selectMode) {
      svg.style('cursor', 'crosshair')

      let startX = 0
      let startY = 0
      let dragging = false
      let rectEl: SVGRectElement | null = null

      const onMouseDown = (e: MouseEvent) => {
        // Ctrl/Cmd + drag → pan (handled by zoom behavior)
        if (e.ctrlKey || e.metaKey) return
        // Only start rect from background, not from nodes
        if ((e.target as Element).tagName !== 'svg') return
        dragging = true
        const rect = svgRef.current!.getBoundingClientRect()
        startX = e.clientX - rect.left
        startY = e.clientY - rect.top
        rectEl = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
        rectEl.setAttribute('x', String(startX))
        rectEl.setAttribute('y', String(startY))
        rectEl.setAttribute('width', '0')
        rectEl.setAttribute('height', '0')
        rectEl.setAttribute('fill', 'rgba(59,130,246,0.1)')
        rectEl.setAttribute('stroke', '#3b82f6')
        rectEl.setAttribute('stroke-dasharray', '4 2')
        rectEl.setAttribute('stroke-width', '1')
        svgRef.current!.appendChild(rectEl)
      }

      const onMouseMove = (e: MouseEvent) => {
        if (!dragging || !rectEl) return
        const rect = svgRef.current!.getBoundingClientRect()
        const curX = e.clientX - rect.left
        const curY = e.clientY - rect.top
        const x = Math.min(startX, curX)
        const y = Math.min(startY, curY)
        const w = Math.abs(curX - startX)
        const h = Math.abs(curY - startY)
        rectEl.setAttribute('x', String(x))
        rectEl.setAttribute('y', String(y))
        rectEl.setAttribute('width', String(w))
        rectEl.setAttribute('height', String(h))
      }

      const onMouseUp = (e: MouseEvent) => {
        if (!dragging || !rectEl) return
        dragging = false
        const svgRect = svgRef.current!.getBoundingClientRect()
        const curX = e.clientX - svgRect.left
        const curY = e.clientY - svgRect.top
        const selX1 = Math.min(startX, curX)
        const selY1 = Math.min(startY, curY)
        const selX2 = Math.max(startX, curX)
        const selY2 = Math.max(startY, curY)

        // Only select if dragged a meaningful distance
        if (selX2 - selX1 > 5 || selY2 - selY1 > 5) {
          // Get current zoom transform
          const g = svg.select('g')
          const transformAttr = g.attr('transform')
          let tx = 0, ty = 0, scale = 1
          if (transformAttr) {
            const match = transformAttr.match(/translate\(([-\d.]+),([-\d.]+)\)\s*scale\(([-\d.]+)\)/)
            if (match) {
              tx = parseFloat(match[1])
              ty = parseFloat(match[2])
              scale = parseFloat(match[3])
            }
          }

          const newSelected = new Set(selectedEntityIds)
          svg.selectAll<SVGGElement, Node>('.nodes g').each(function (d) {
            // Convert node position to screen coordinates
            const screenX = (d.x || 0) * scale + tx
            const screenY = (d.y || 0) * scale + ty
            if (screenX >= selX1 && screenX <= selX2 && screenY >= selY1 && screenY <= selY2) {
              newSelected.add(d.id)
            }
          })
          setSelectedEntityIds(newSelected)
        }

        rectEl.remove()
        rectEl = null
      }

      const svgEl = svgRef.current
      svgEl.addEventListener('mousedown', onMouseDown)
      window.addEventListener('mousemove', onMouseMove)
      window.addEventListener('mouseup', onMouseUp)

      return () => {
        svgEl.removeEventListener('mousedown', onMouseDown)
        window.removeEventListener('mousemove', onMouseMove)
        window.removeEventListener('mouseup', onMouseUp)
        svg.style('cursor', null)
      }
    } else {
      svg.style('cursor', null)
    }
  }, [selectMode, selectedEntityIds])

  // Highlight selected entity node (separate effect to avoid rebuilding simulation)
  useEffect(() => {
    if (!svgRef.current) return
    const svg = select(svgRef.current)
    const selectedId = selectedEntity?.id

    svg.selectAll<SVGGElement, Node>('.nodes g').each(function (d) {
      const circle = select(this).select('circle')
      if (d.id === selectedId) {
        circle
          .attr('r', 40)
          .attr('stroke', '#fbbf24')
          .attr('stroke-width', 3)
      } else {
        circle
          .attr('r', 30)
          .attr('stroke', '#fff')
          .attr('stroke-width', 2)
      }
    })
  }, [selectedEntity])

  // Highlight multi-selected nodes
  useEffect(() => {
    if (!svgRef.current) return
    const svg = select(svgRef.current)

    svg.selectAll<SVGGElement, Node>('.nodes g').each(function (d) {
      const circle = select(this).select('circle')
      // Don't override the single-selected highlight
      if (d.id === selectedEntity?.id) return

      if (selectedEntityIds.has(d.id)) {
        circle
          .attr('stroke', '#fbbf24')
          .attr('stroke-width', 2)
          .attr('stroke-dasharray', '4 2')
      } else {
        circle
          .attr('stroke', '#fff')
          .attr('stroke-width', 2)
          .attr('stroke-dasharray', null)
      }
    })
  }, [selectedEntityIds, selectedEntity])

  // Keyboard shortcuts: Escape to clear selection and exit select mode
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelectedEntityIds(new Set())
        setSelectMode(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Select mode: enable drag-to-select rectangle and click-to-toggle
  useEffect(() => {
    if (!svgRef.current) return
    const svg = select(svgRef.current)

    if (selectMode) {
      svg.style('cursor', 'crosshair')

      let startX = 0
      let startY = 0
      let dragging = false
      let rectEl: SVGRectElement | null = null

      const onMouseDown = (e: MouseEvent) => {
        // Ctrl/Cmd + drag → pan (handled by zoom behavior)
        if (e.ctrlKey || e.metaKey) return
        // Only start rect from background, not from nodes
        if ((e.target as Element).tagName !== 'svg') return
        dragging = true
        const rect = svgRef.current!.getBoundingClientRect()
        startX = e.clientX - rect.left
        startY = e.clientY - rect.top
        rectEl = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
        rectEl.setAttribute('x', String(startX))
        rectEl.setAttribute('y', String(startY))
        rectEl.setAttribute('width', '0')
        rectEl.setAttribute('height', '0')
        rectEl.setAttribute('fill', 'rgba(59,130,246,0.1)')
        rectEl.setAttribute('stroke', '#3b82f6')
        rectEl.setAttribute('stroke-dasharray', '4 2')
        rectEl.setAttribute('stroke-width', '1')
        svgRef.current!.appendChild(rectEl)
      }

      const onMouseMove = (e: MouseEvent) => {
        if (!dragging || !rectEl) return
        const rect = svgRef.current!.getBoundingClientRect()
        const curX = e.clientX - rect.left
        const curY = e.clientY - rect.top
        const x = Math.min(startX, curX)
        const y = Math.min(startY, curY)
        const w = Math.abs(curX - startX)
        const h = Math.abs(curY - startY)
        rectEl.setAttribute('x', String(x))
        rectEl.setAttribute('y', String(y))
        rectEl.setAttribute('width', String(w))
        rectEl.setAttribute('height', String(h))
      }

      const onMouseUp = (e: MouseEvent) => {
        if (!dragging || !rectEl) return
        dragging = false
        const svgRect = svgRef.current!.getBoundingClientRect()
        const curX = e.clientX - svgRect.left
        const curY = e.clientY - svgRect.top
        const selX1 = Math.min(startX, curX)
        const selY1 = Math.min(startY, curY)
        const selX2 = Math.max(startX, curX)
        const selY2 = Math.max(startY, curY)

        // Only select if dragged a meaningful distance
        if (selX2 - selX1 > 5 || selY2 - selY1 > 5) {
          // Get current zoom transform
          const g = svg.select('g')
          const transformAttr = g.attr('transform')
          let tx = 0, ty = 0, scale = 1
          if (transformAttr) {
            const match = transformAttr.match(/translate\(([-\d.]+),([-\d.]+)\)\s*scale\(([-\d.]+)\)/)
            if (match) {
              tx = parseFloat(match[1])
              ty = parseFloat(match[2])
              scale = parseFloat(match[3])
            }
          }

          const newSelected = new Set(selectedEntityIds)
          svg.selectAll<SVGGElement, Node>('.nodes g').each(function (d) {
            // Convert node position to screen coordinates
            const screenX = (d.x || 0) * scale + tx
            const screenY = (d.y || 0) * scale + ty
            if (screenX >= selX1 && screenX <= selX2 && screenY >= selY1 && screenY <= selY2) {
              newSelected.add(d.id)
            }
          })
          setSelectedEntityIds(newSelected)
        }

        rectEl.remove()
        rectEl = null
      }

      const svgEl = svgRef.current
      svgEl.addEventListener('mousedown', onMouseDown)
      window.addEventListener('mousemove', onMouseMove)
      window.addEventListener('mouseup', onMouseUp)

      return () => {
        svgEl.removeEventListener('mousedown', onMouseDown)
        window.removeEventListener('mousemove', onMouseMove)
        window.removeEventListener('mouseup', onMouseUp)
        svg.style('cursor', null)
      }
    } else {
      svg.style('cursor', null)
    }
  }, [selectMode, selectedEntityIds])

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
    svg.transition().duration(300).call(zoomBehaviorRef.current.transform, zoomIdentity)
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

  const handleDeleteEntity = useCallback(
    (entityId: string) => {
      setEntities((prev) => prev.filter((e) => e.id !== entityId))
      setRelations((prev) =>
        prev.filter(
          (r) => r.source_entity_id !== entityId && r.target_entity_id !== entityId
        )
      )
      setSelectedEntityIds((prev) => {
        const next = new Set(prev)
        next.delete(entityId)
        return next
      })
    },
    []
  )

  const handleDeleteRelation = useCallback((relationId: string) => {
    setRelations((prev) => prev.filter((r) => r.id !== relationId))
  }, [])

  const handleDeleteSelected = useCallback(async () => {
    const ids = Array.from(selectedEntityIds)
    try {
      await Promise.all(ids.map((id) => memoriesApi.deleteEntity(id)))
      toast.success(t('deleteEntitySuccess'))
      setEntities((prev) => prev.filter((e) => !selectedEntityIds.has(e.id)))
      setRelations((prev) =>
        prev.filter(
          (r) =>
            !selectedEntityIds.has(r.source_entity_id) &&
            !selectedEntityIds.has(r.target_entity_id)
        )
      )
      setSelectedEntityIds(new Set())
    } catch {
      // error toast handled by interceptor
    }
  }, [selectedEntityIds, t])

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-muted-foreground">{tCommon('loading')}</div>
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
          selectMode={selectMode}
          onToggleSelectMode={() => {
            setSelectMode((prev) => {
              if (prev) setSelectedEntityIds(new Set())
              return !prev
            })
          }}
          selectedCount={selectedEntityIds.size}
          onDeleteSelected={handleDeleteSelected}
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
        onDeleteEntity={handleDeleteEntity}
        onDeleteRelation={handleDeleteRelation}
      />
    </div>
  )
}
