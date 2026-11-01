/**
 * Isometric 2.5D Virtual AI Office Canvas Engine (60 FPS)
 * Features:
 *   1. Ramon's Private Executive Boss Office (Crimson/Gold Carpet, Boss Desk at 15,2, Doorway at 13,3).
 *   2. Solid Wall Segments with Open Doorways + Depth-Sorted 3D Wall Occlusion.
 *   3. A* Pathfinding Engine: Agents walk strictly around walls and through doorways (NEVER through walls!).
 *   4. Visual Rule:
 *      - IDLE agents: Stand up and SLOWLY walk around the office via A* paths.
 *      - WORKING agents: Walk via A* to their desk, SIT in their chair facing the monitor, and type.
 */

class IsometricOfficeEngine {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.gridW = 19;
    this.gridH = 14;
    this.tileW = 56;
    this.tileH = 28;
    this.scale = 1.0;
    this.panX = 0;
    this.panY = 0;
    this.showGridCoords = false;

    this.isDragging = false;
    this.draggingItem = null;
    this.hoveredFurniture = null;
    this.buildTool = null; // null = Move/Drag mode, or {kind, label, color}
    this.dragStartX = 0;
    this.dragStartY = 0;
    this.hoverTile = null;
    this.animTick = 0;

    this.agents = [];
    this.furniture = [];
    this.floorTiles = {};
    this.isPaintingTiles = false;
    this.lastPaintedTileKey = '';
    this.activeFloor = 1;
    this.selectedAgentId = 'ramon';

    this.workingUntilTick = {};
    this.wanderState = {};

    // Build solid wall segments & blocked edge map from editable furniture items!
    this.wallSegments = [];
    this.blockedEdges = new Set(); // key: "x1,y1->x2,y2"
    this._initWallsAndDoorways();

    this.idleWaypoints = [
      { x: 2, y: 3, label: 'Water Cooler' },
      { x: 5, y: 2, label: 'War Room' },
      { x: 8, y: 11, label: 'Ping-Pong Left' },
      { x: 11, y: 11, label: 'Ping-Pong Right' },
      { x: 11, y: 8, label: 'Break Lounge' },
      { x: 12, y: 5, label: 'Hallway North' },
      { x: 15, y: 8, label: 'Gym Treadmill' },
      { x: 7, y: 7, label: 'Center Hallway' },
      { x: 4, y: 11, label: 'South Walkway' },
      { x: 2, y: 6, label: 'Server Rack Bay' },
    ];

    this._bindEvents();
    this.resize();
    window.addEventListener('resize', () => this.resize());
    requestAnimationFrame(() => this.loop());
  }

  _blockEdge(x1, y1, x2, y2) {
    this.blockedEdges.add(`${x1},${y1}->${x2},${y2}`);
    this.blockedEdges.add(`${x2},${y2}->${x1},${y1}`);
  }

  _initWallsAndDoorways() {
    this.wallSegments = [];
    this.blockedEdges.clear();

    // All walls & doorways are now 100% editable FurnitureItems on the active floor!
    const floorItems = (this.furniture || []).filter((f) => f.floor === this.activeFloor);
    for (const item of floorItems) {
      const gx = Math.round(item.grid_x);
      const gy = Math.round(item.grid_y);
      if (item.kind === 'wall_ew') {
        // North-edge wall on tile (gx, gy): blocks walking between (gx, gy-1) and (gx, gy)
        this._blockEdge(gx, gy - 1, gx, gy);
      } else if (item.kind === 'wall_ns') {
        // West-edge wall on tile (gx, gy): blocks walking between (gx-1, gy) and (gx, gy)
        this._blockEdge(gx - 1, gy, gx, gy);
      }
    }
    // User-placed doorways unblock edges at that tile so agents can walk through!
    for (const item of floorItems) {
      if (item.kind === 'door') {
        const gx = Math.round(item.grid_x);
        const gy = Math.round(item.grid_y);
        for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
          this.blockedEdges.delete(`${gx},${gy}->${gx + dx},${gy + dy}`);
          this.blockedEdges.delete(`${gx + dx},${gy + dy}->${gx},${gy}`);
        }
      }
    }
  }

  /**
   * A* Grid Pathfinding respecting all walls and doorways (4-directional orthogonal steps so agents never clip corners)
   */
  findPath(startX, startY, endX, endY) {
    const sx = Math.max(1, Math.min(this.gridW - 2, Math.round(startX)));
    const sy = Math.max(1, Math.min(this.gridH - 2, Math.round(startY)));
    const tx = Math.max(1, Math.min(this.gridW - 2, Math.round(endX)));
    const ty = Math.max(1, Math.min(this.gridH - 2, Math.round(endY)));

    if (sx === tx && sy === ty) return [{ x: tx, y: ty }];

    const open = [{ x: sx, y: sy, g: 0, f: Math.abs(tx - sx) + Math.abs(ty - sy) }];
    const cameFrom = new Map();
    const gScore = new Map([[`${sx},${sy}`, 0]]);
    const closed = new Set();

    const dirs = [
      { dx: 1, dy: 0 },
      { dx: -1, dy: 0 },
      { dx: 0, dy: 1 },
      { dx: 0, dy: -1 },
    ];

    while (open.length > 0) {
      open.sort((a, b) => a.f - b.f);
      const curr = open.shift();
      const cKey = `${curr.x},${curr.y}`;

      if (curr.x === tx && curr.y === ty) {
        const path = [];
        let k = cKey;
        while (k) {
          const [px, py] = k.split(',').map(Number);
          path.unshift({ x: px, y: py });
          k = cameFrom.get(k);
        }
        return path.length > 1 ? path.slice(1) : path;
      }

      closed.add(cKey);

      for (const { dx, dy } of dirs) {
        const nx = curr.x + dx;
        const ny = curr.y + dy;
        if (nx < 1 || nx >= this.gridW - 1 || ny < 1 || ny >= this.gridH - 1) continue;

        const nKey = `${nx},${ny}`;
        if (closed.has(nKey)) continue;

        // Check if a wall blocks the edge between (curr.x, curr.y) and (nx, ny)
        if (this.blockedEdges.has(`${curr.x},${curr.y}->${nx},${ny}`)) continue;

        const tentativeG = curr.g + 1;
        if (tentativeG < (gScore.get(nKey) ?? Infinity)) {
          cameFrom.set(nKey, cKey);
          gScore.set(nKey, tentativeG);
          const f = tentativeG + Math.abs(tx - nx) + Math.abs(ty - ny);
          if (!open.some((n) => n.x === nx && n.y === ny)) {
            open.push({ x: nx, y: ny, g: tentativeG, f });
          }
        }
      }
    }

    return [{ x: tx, y: ty }];
  }

  resize() {
    if (!this.canvas) return;
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (this.panX === 0 && this.panY === 0) {
      this.resetCamera();
    }
  }

  resetCamera() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.scale = 1.0;
    this.panX = rect.width * 0.47;
    this.panY = rect.height * 0.14;
  }

  zoom(factor) {
    this.scale = Math.max(0.55, Math.min(1.85, this.scale * factor));
  }

  toggleGrid() {
    this.showGridCoords = !this.showGridCoords;
  }

  gridToScreen(gx, gy, gz = 0) {
    const tw = this.tileW * this.scale;
    const th = this.tileH * this.scale;
    const sx = this.panX + (gx - gy) * (tw / 2);
    const sy = this.panY + (gx + gy) * (th / 2) - gz * this.scale;
    return { x: sx, y: sy };
  }

  screenToGrid(sx, sy) {
    const tw = this.tileW * this.scale;
    const th = this.tileH * this.scale;
    const dx = sx - this.panX;
    const dy = sy - this.panY;
    const gx = (dx / (tw / 2) + dy / (th / 2)) / 2;
    const gy = (dy / (th / 2) - dx / (tw / 2)) / 2;
    return { gx: Math.floor(gx), gy: Math.floor(gy) };
  }

  _findFurnitureAt(mx, my) {
    const tile = this.screenToGrid(mx, my);
    const floorFurniture = (this.furniture || []).filter((f) => f.floor === this.activeFloor);
    let best = null;
    let bestDist = 32 * this.scale;
    for (const item of floorFurniture) {
      // Compute visual center of each item (walls sit on the North or West edge of their tile)
      const cx = item.kind === 'wall_ns' ? item.grid_x + 0.1 : item.grid_x + 0.5;
      const cy = item.kind === 'wall_ew' ? item.grid_y + 0.1 : item.grid_y + 0.5;
      const pos = this.gridToScreen(cx, cy, 14);
      const d = Math.hypot(mx - pos.x, my - pos.y);
      if (d < bestDist) {
        bestDist = d;
        best = item;
      }
    }
    if (best) return best;
    return floorFurniture.find(
      (f) => Math.round(f.grid_x) === tile.gx && Math.round(f.grid_y) === tile.gy
    ) || null;
  }

  _bindEvents() {
    let moved = false;

    // Keyboard shortcut 'R' to rotate hovered/dragged item (or active placement tool)
    window.addEventListener('keydown', (e) => {
      const tag = (e.target && e.target.tagName) || '';
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (e.key === 'r' || e.key === 'R') {
        e.preventDefault();
        const targetItem = this.draggingItem || this.hoveredFurniture;
        if (targetItem && window.app) {
          window.app.rotateFurnitureItem(targetItem.id);
        } else if (this.buildTool && window.app) {
          if (this.buildTool.kind === 'wall_ew') {
            this.buildTool.kind = 'wall_ns';
            this.buildTool.label = 'Wall (Front-Back)';
          } else if (this.buildTool.kind === 'wall_ns') {
            this.buildTool.kind = 'wall_ew';
            this.buildTool.label = 'Wall (Left-Right)';
          } else {
            this.buildTool.rotation = ((this.buildTool.rotation || 0) + 1) % 4;
          }
          window.app.setBuildTool(this.buildTool);
        }
      }
    });

    this.canvas.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return; // left click only for drag/pan
      const rect = this.canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      moved = false;

      // If Floor Tile Paint tool is active, start painting on mousedown + drag!
      if (this.buildTool && this.buildTool.kind === 'tile') {
        this.isPaintingTiles = true;
        const tile = this.screenToGrid(mx, my);
        if (tile.gx >= 0 && tile.gx < this.gridW && tile.gy >= 0 && tile.gy < this.gridH) {
          this.lastPaintedTileKey = `${this.activeFloor}:${tile.gx},${tile.gy}`;
          if (window.app) {
            window.app.paintFloorTileAt(tile.gx, tile.gy, this.buildTool.tileStyle);
          }
        }
        return;
      }

      // If no placement/delete/rotate tool is active, check if user grabbed a furniture/wall item to drag it!
      if (!this.buildTool) {
        const hitItem = this._findFurnitureAt(mx, my);
        if (hitItem) {
          this.draggingItem = hitItem;
          this.dragOrigX = hitItem.grid_x;
          this.dragOrigY = hitItem.grid_y;
          this.canvas.style.cursor = 'grabbing';
          return;
        }
      }

      this.isDragging = true;
      this.dragStartX = e.clientX - this.panX;
      this.dragStartY = e.clientY - this.panY;
    });

    window.addEventListener('mousemove', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      this.hoverTile = this.screenToGrid(mx, my);
      this.hoveredFurniture = this._findFurnitureAt(mx, my);

      // Continuous drag-painting of floor tiles!
      if (this.isPaintingTiles && this.buildTool && this.buildTool.kind === 'tile' && this.hoverTile) {
        const { gx, gy } = this.hoverTile;
        if (gx >= 0 && gx < this.gridW && gy >= 0 && gy < this.gridH) {
          const key = `${this.activeFloor}:${gx},${gy}`;
          if (key !== this.lastPaintedTileKey) {
            this.lastPaintedTileKey = key;
            if (window.app) {
              window.app.paintFloorTileAt(gx, gy, this.buildTool.tileStyle);
            }
          }
        }
        return;
      }

      if (this.draggingItem && this.hoverTile) {
        const nx = Math.max(1, Math.min(this.gridW - 1, this.hoverTile.gx));
        const ny = Math.max(1, Math.min(this.gridH - 1, this.hoverTile.gy));
        if (nx !== this.draggingItem.grid_x || ny !== this.draggingItem.grid_y) {
          moved = true;
          this.draggingItem.grid_x = nx;
          this.draggingItem.grid_y = ny;
          if (this.draggingItem.kind === 'desk' && this.draggingItem.assigned_agent_id) {
            const ag = this.agents.find((a) => a.id === this.draggingItem.assigned_agent_id);
            if (ag) {
              ag.desk_x = nx;
              ag.desk_y = ny;
            }
          }
          this._initWallsAndDoorways();
        }
        return;
      }

      if (this.isDragging) {
        moved = true;
        this.panX = e.clientX - this.dragStartX;
        this.panY = e.clientY - this.dragStartY;
      } else {
        if (this.buildTool) {
          this.canvas.style.cursor =
            this.buildTool.kind === 'delete'
              ? 'not-allowed'
              : this.buildTool.kind === 'rotate'
                ? 'pointer'
                : 'copy';
        } else if (this.hoveredFurniture) {
          this.canvas.style.cursor = 'grab';
        } else {
          this.canvas.style.cursor = 'default';
        }
      }
    });

    window.addEventListener('mouseup', (e) => {
      if (this.isPaintingTiles) {
        this.isPaintingTiles = false;
        this.lastPaintedTileKey = '';
        return;
      }

      if (this.draggingItem) {
        const item = this.draggingItem;
        this.draggingItem = null;
        this.canvas.style.cursor = 'default';
        if (moved && window.app) {
          window.app.moveFurnitureItem(item.id, item.grid_x, item.grid_y);
        } else if (!moved) {
          const rect = this.canvas.getBoundingClientRect();
          this._handleCanvasClick(e.clientX - rect.left, e.clientY - rect.top);
        }
        return;
      }

      if (this.isDragging && !moved) {
        const rect = this.canvas.getBoundingClientRect();
        this._handleCanvasClick(e.clientX - rect.left, e.clientY - rect.top);
      }
      this.isDragging = false;
    });

    // Right-click on any furniture/wall item to delete it (or cancel build tool)
    this.canvas.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      const rect = this.canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const hitItem = this._findFurnitureAt(mx, my);
      if (hitItem && window.app) {
        window.app.deleteFurnitureItem(hitItem.id);
        return;
      }
      if (this.buildTool && window.app) {
        window.app.setBuildTool(null);
      }
    });

    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      this.zoom(e.deltaY < 0 ? 1.08 : 0.92);
    }, { passive: false });
  }

  _handleCanvasClick(mx, my) {
    const tile = this.screenToGrid(mx, my);

    // 1. If Delete Tool is active, clicking an item/wall deletes it
    if (this.buildTool && this.buildTool.kind === 'delete') {
      const hitItem = this._findFurnitureAt(mx, my);
      if (hitItem && window.app) {
        window.app.deleteFurnitureItem(hitItem.id);
      }
      return;
    }

    // 2. If Rotate Tool is active, clicking an item/wall rotates it 90°
    if (this.buildTool && this.buildTool.kind === 'rotate') {
      const hitItem = this._findFurnitureAt(mx, my);
      if (hitItem && window.app) {
        window.app.rotateFurnitureItem(hitItem.id);
      }
      return;
    }

    // 3. If Floor Tile Tool is active, paint that tile
    if (this.buildTool && this.buildTool.kind === 'tile') {
      if (tile.gx >= 0 && tile.gx < this.gridW && tile.gy >= 0 && tile.gy < this.gridH) {
        if (window.app) {
          window.app.paintFloorTileAt(tile.gx, tile.gy, this.buildTool.tileStyle);
        }
      }
      return;
    }

    // 4. If a Place Furniture Tool is active, clicking a tile places that item there!
    if (this.buildTool) {
      if (tile.gx >= 1 && tile.gx < this.gridW && tile.gy >= 1 && tile.gy < this.gridH) {
        if (window.app) {
          window.app.placeFurnitureAt(
            this.buildTool.kind,
            this.buildTool.label,
            this.buildTool.color,
            tile.gx,
            tile.gy,
            this.buildTool.rotation || 0
          );
        }
      }
      return;
    }

    // 5. Normal mode: click agent avatar to select, or click tile to walk
    const floorAgents = this.agents.filter((a) => a.floor === this.activeFloor);
    for (const agent of floorAgents) {
      const pos = this.gridToScreen(agent.current_x + 0.5, agent.current_y + 0.7, 22);
      const dist = Math.hypot(mx - pos.x, my - pos.y);
      if (dist < 30 * this.scale) {
        if (window.app) window.app.selectAgent(agent.id);
        return;
      }
    }

    if (tile.gx >= 1 && tile.gx < this.gridW - 1 && tile.gy >= 1 && tile.gy < this.gridH - 1) {
      if (window.app) {
        window.app.walkSelectedAgentTo(tile.gx, tile.gy);
      }
    }
  }

  markAgentWorking(agentId, durationFrames = 1100) {
    this.workingUntilTick[agentId] = this.animTick + durationFrames;
    const ag = this.agents.find((a) => a.id === agentId);
    if (ag) {
      this._assignAgentPathTo(ag, ag.desk_x, ag.desk_y);
    }
  }

  isAgentInWorkMode(agent) {
    return (
      agent.status === 'working' ||
      (this.workingUntilTick[agent.id] || 0) > this.animTick
    );
  }

  isAgentSeatedWorkingAtDesk(agent) {
    if (!this.isAgentInWorkMode(agent)) return false;
    const distToDesk = Math.hypot(agent.current_x - agent.desk_x, agent.current_y - agent.desk_y);
    return distToDesk < 0.25;
  }

  _assignAgentPathTo(agent, destX, destY) {
    const wState = this.wanderState[agent.id] || {
      path: [],
      finalX: destX,
      finalY: destY,
      pauseUntilTick: 0,
      stepPhase: 0,
      facing: 1,
    };
    const rx = Math.round(destX);
    const ry = Math.round(destY);
    if (wState.finalX !== rx || wState.finalY !== ry || !wState.path || wState.path.length === 0) {
      wState.finalX = rx;
      wState.finalY = ry;
      wState.path = this.findPath(agent.current_x, agent.current_y, rx, ry);
    }
    agent.target_x = rx;
    agent.target_y = ry;
    this.wanderState[agent.id] = wState;
  }

  _pickNewWanderTarget(agent, idxHint = 0) {
    const pickIdx = (Math.floor(Math.random() * this.idleWaypoints.length) + idxHint) % this.idleWaypoints.length;
    const wp = this.idleWaypoints[pickIdx];
    this._assignAgentPathTo(agent, wp.x, wp.y);
    this.wanderState[agent.id].pauseUntilTick = 0;
  }

  syncState(agents, furniture, activeFloor, selectedAgentId, floorTiles) {
    const prevMap = new Map(this.agents.map((a) => [a.id, a]));
    this.agents = agents.map((a, idx) => {
      const prev = prevMap.get(a.id);
      if (!prev) {
        const startWp = this.idleWaypoints[idx % this.idleWaypoints.length];
        const copy = {
          ...a,
          current_x: startWp.x,
          current_y: startWp.y,
        };
        this._pickNewWanderTarget(copy, idx + 2);
        return copy;
      }

      const prevTurns = (prev.telemetry && prev.telemetry.turns) || 0;
      const newTurns = (a.telemetry && a.telemetry.turns) || 0;
      const merged = {
        ...a,
        current_x: prev.current_x,
        current_y: prev.current_y,
        target_x: prev.target_x,
        target_y: prev.target_y,
      };
      if (newTurns > prevTurns || a.status === 'working') {
        this.workingUntilTick[a.id] = this.animTick + 1100;
        this._assignAgentPathTo(merged, a.desk_x, a.desk_y);
      }
      return merged;
    });
    this.furniture = (furniture || []).map((f) => {
      if (this.draggingItem && this.draggingItem.id === f.id) {
        return { ...f, grid_x: this.draggingItem.grid_x, grid_y: this.draggingItem.grid_y };
      }
      return f;
    });
    if (floorTiles) {
      this.floorTiles = floorTiles;
    }
    this.activeFloor = activeFloor || 1;
    this.selectedAgentId = selectedAgentId || this.selectedAgentId;
    this._initWallsAndDoorways();
  }

  loop() {
    this.animTick += 1;
    this._stepPhysics();
    this.render();
    requestAnimationFrame(() => this.loop());
  }

  _stepPhysics() {
    for (let idx = 0; idx < this.agents.length; idx++) {
      const agent = this.agents[idx];
      if (!this.wanderState[agent.id]) {
        this._pickNewWanderTarget(agent, idx);
      }
      const wState = this.wanderState[agent.id];
      const workingNow = this.isAgentInWorkMode(agent);

      if (workingNow) {
        // Ensure A* path leads into their office/desk through the doorway!
        if (wState.finalX !== agent.desk_x || wState.finalY !== agent.desk_y) {
          this._assignAgentPathTo(agent, agent.desk_x, agent.desk_y);
        }
      } else {
        // When idle, if path is finished, pause briefly then pick a new waypoint via A*
        if (!wState.path || wState.path.length === 0) {
          if (wState.pauseUntilTick === 0) {
            wState.pauseUntilTick = this.animTick + 90 + idx * 20;
          } else if (this.animTick >= wState.pauseUntilTick) {
            this._pickNewWanderTarget(agent, idx + this.animTick);
          }
        }
      }

      // Step along the next A* node in wState.path
      if (wState.path && wState.path.length > 0) {
        const nextNode = wState.path[0];
        const dx = nextNode.x - agent.current_x;
        const dy = nextNode.y - agent.current_y;
        const dist = Math.hypot(dx, dy);

        if (dist > 0.03) {
          const speed = workingNow ? 0.035 : 0.017;
          agent.current_x += (dx / dist) * Math.min(speed, dist);
          agent.current_y += (dy / dist) * Math.min(speed, dist);
          wState.stepPhase = (wState.stepPhase || 0) + (workingNow ? 0.26 : 0.16);
          wState.isMoving = true;
          wState.facing = dx - dy >= 0 ? 1 : -1;
        } else {
          agent.current_x = nextNode.x;
          agent.current_y = nextNode.y;
          wState.path.shift();
          if (wState.path.length === 0) {
            wState.isMoving = false;
          }
        }
      } else {
        wState.isMoving = false;
      }
    }
  }

  render() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const ctx = this.ctx;
    ctx.clearRect(0, 0, rect.width, rect.height);

    this._drawFloorBase(ctx);
    this._drawBackWalls(ctx);

    // Depth-sort Walls, Furniture, and Agents accurately so North/West walls sit BEHIND items on the same tile!
    const drawables = [];

    const floorFurniture = this.furniture.filter((f) => f.floor === this.activeFloor);
    for (const item of floorFurniture) {
      // North/West edge walls have depth +0.12 so they never clip plants/items sitting inside (gx, gy) (+0.65)!
      const isEdgeWall = item.kind === 'wall_ew' || item.kind === 'wall_ns' || item.kind === 'door';
      drawables.push({
        depth: item.grid_x + item.grid_y + (isEdgeWall ? 0.12 : 0.65),
        type: 'furniture',
        item,
      });
    }

    const floorAgents = this.agents.filter((a) => a.floor === this.activeFloor);
    for (const agent of floorAgents) {
      drawables.push({
        depth: agent.current_x + agent.current_y + 0.72,
        type: 'agent',
        agent,
      });
    }

    drawables.sort((a, b) => a.depth - b.depth);

    for (const d of drawables) {
      if (d.type === 'furniture') {
        this._drawFurnitureItem(ctx, d.item);
      } else {
        this._drawAgentAvatar(ctx, d.agent);
      }
    }

    this._drawCollaborationBeams(ctx, floorAgents);
  }

  _drawFloorBase(ctx) {
    const pLeft = this.gridToScreen(0, this.gridH, 0);
    const pBottom = this.gridToScreen(this.gridW, this.gridH, 0);
    const pRight = this.gridToScreen(this.gridW, 0, 0);

    ctx.fillStyle = '#5c3c20';
    ctx.beginPath();
    ctx.moveTo(pLeft.x, pLeft.y);
    ctx.lineTo(pBottom.x, pBottom.y);
    ctx.lineTo(pBottom.x, pBottom.y + 12 * this.scale);
    ctx.lineTo(pLeft.x, pLeft.y + 12 * this.scale);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = '#472d16';
    ctx.beginPath();
    ctx.moveTo(pBottom.x, pBottom.y);
    ctx.lineTo(pRight.x, pRight.y);
    ctx.lineTo(pRight.x, pRight.y + 12 * this.scale);
    ctx.lineTo(pBottom.x, pBottom.y + 12 * this.scale);
    ctx.closePath();
    ctx.fill();

    for (let gx = 0; gx < this.gridW; gx++) {
      for (let gy = 0; gy < this.gridH; gy++) {
        const c0 = this.gridToScreen(gx, gy);
        const c1 = this.gridToScreen(gx + 1, gy);
        const c2 = this.gridToScreen(gx + 1, gy + 1);
        const c3 = this.gridToScreen(gx, gy + 1);

        const tileStyle = (this.floorTiles && this.floorTiles[`${this.activeFloor}:${gx},${gy}`]) || 'wood';
        const isHover = this.hoverTile && this.hoverTile.gx === gx && this.hoverTile.gy === gy;
        const even = (gx + gy) % 2 === 0;

        if (isHover) {
          ctx.fillStyle = '#fde047';
        } else if (tileStyle === 'gold_doorway') {
          ctx.fillStyle = '#d97706';
        } else if (tileStyle === 'crimson_boss') {
          ctx.fillStyle = even ? '#5c1d24' : '#4c171d';
        } else if (tileStyle === 'slate_cubicle') {
          ctx.fillStyle = even ? '#6e7685' : '#636b78';
        } else if (tileStyle === 'dark_gym') {
          ctx.fillStyle = even ? '#1e2430' : '#181d27';
        } else if (tileStyle === 'marble_white') {
          ctx.fillStyle = even ? '#e2e8f0' : '#cbd5e1';
        } else if (tileStyle === 'emerald_turf') {
          ctx.fillStyle = even ? '#065f46' : '#047857';
        } else if (tileStyle === 'checker_tech') {
          ctx.fillStyle = even ? '#312e81' : '#1e1b4b';
        } else {
          ctx.fillStyle = even ? '#b89466' : '#ad895c';
        }

        ctx.beginPath();
        ctx.moveTo(c0.x, c0.y);
        ctx.lineTo(c1.x, c1.y);
        ctx.lineTo(c2.x, c2.y);
        ctx.lineTo(c3.x, c3.y);
        ctx.closePath();
        ctx.fill();

        ctx.strokeStyle =
          tileStyle === 'crimson_boss'
            ? 'rgba(251, 191, 36, 0.18)'
            : tileStyle === 'dark_gym'
              ? 'rgba(255,255,255,0.06)'
              : tileStyle === 'marble_white'
                ? 'rgba(100,116,139,0.28)'
                : 'rgba(92, 60, 32, 0.28)';
        ctx.lineWidth = 0.8;
        ctx.stroke();

        if (this.showGridCoords && gx % 2 === 0 && gy % 2 === 0) {
          ctx.fillStyle = 'rgba(255,255,255,0.55)';
          ctx.font = `${Math.round(8 * this.scale)}px monospace`;
          ctx.fillText(`${gx},${gy}`, c0.x - 8, c0.y + 14);
        }
      }
    }
  }

  _drawBackWalls(ctx) {
    const wallH = 38;
    for (let gy = 0; gy < this.gridH; gy++) {
      const b0 = this.gridToScreen(0, gy, 0);
      const b1 = this.gridToScreen(0, gy + 1, 0);
      const t1 = this.gridToScreen(0, gy + 1, wallH);
      const t0 = this.gridToScreen(0, gy, wallH);

      ctx.fillStyle = gy % 2 === 0 ? '#7c3f23' : '#6e361d';
      ctx.beginPath();
      ctx.moveTo(b0.x, b0.y);
      ctx.lineTo(b1.x, b1.y);
      ctx.lineTo(t1.x, t1.y);
      ctx.lineTo(t0.x, t0.y);
      ctx.closePath();
      ctx.fill();
    }

    for (let gx = 0; gx < this.gridW; gx++) {
      const b0 = this.gridToScreen(gx, 0, 0);
      const b1 = this.gridToScreen(gx + 1, 0, 0);
      const t1 = this.gridToScreen(gx + 1, 0, wallH);
      const t0 = this.gridToScreen(gx, 0, wallH);

      ctx.fillStyle = gx % 2 === 0 ? '#68321a' : '#5c2b16';
      ctx.beginPath();
      ctx.moveTo(b0.x, b0.y);
      ctx.lineTo(b1.x, b1.y);
      ctx.lineTo(t1.x, t1.y);
      ctx.lineTo(t0.x, t0.y);
      ctx.closePath();
      ctx.fill();
    }
  }

  _drawIsoBox(ctx, gx, gy, w, d, h, topCol, leftCol, rightCol, baseZ = 0) {
    const b0 = this.gridToScreen(gx, gy, baseZ);
    const b1 = this.gridToScreen(gx + w, gy, baseZ);
    const b2 = this.gridToScreen(gx + w, gy + d, baseZ);
    const b3 = this.gridToScreen(gx, gy + d, baseZ);

    const t0 = this.gridToScreen(gx, gy, baseZ + h);
    const t1 = this.gridToScreen(gx + w, gy, baseZ + h);
    const t2 = this.gridToScreen(gx + w, gy + d, baseZ + h);
    const t3 = this.gridToScreen(gx, gy + d, baseZ + h);

    ctx.fillStyle = leftCol;
    ctx.beginPath();
    ctx.moveTo(b3.x, b3.y);
    ctx.lineTo(b2.x, b2.y);
    ctx.lineTo(t2.x, t2.y);
    ctx.lineTo(t3.x, t3.y);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = rightCol;
    ctx.beginPath();
    ctx.moveTo(b2.x, b2.y);
    ctx.lineTo(b1.x, b1.y);
    ctx.lineTo(t1.x, t1.y);
    ctx.lineTo(t2.x, t2.y);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = topCol;
    ctx.beginPath();
    ctx.moveTo(t0.x, t0.y);
    ctx.lineTo(t1.x, t1.y);
    ctx.lineTo(t2.x, t2.y);
    ctx.lineTo(t3.x, t3.y);
    ctx.closePath();
    ctx.fill();
  }

  _drawFurnitureItem(ctx, item) {
    const { gx, gy } = { gx: item.grid_x, gy: item.grid_y };
    const rot = ((item.rotation || 0) % 4 + 4) % 4;
    const isHovered = this.hoveredFurniture && this.hoveredFurniture.id === item.id;
    const isBeingDragged = this.draggingItem && this.draggingItem.id === item.id;

    // Highlight tile base if item is hovered or being dragged
    if (isHovered || isBeingDragged) {
      const c0 = this.gridToScreen(gx, gy, 0.5);
      const c1 = this.gridToScreen(gx + 1, gy, 0.5);
      const c2 = this.gridToScreen(gx + 1, gy + 1, 0.5);
      const c3 = this.gridToScreen(gx, gy + 1, 0.5);
      const isDeleteMode = this.buildTool && this.buildTool.kind === 'delete';
      const isRotateMode = this.buildTool && this.buildTool.kind === 'rotate';
      ctx.strokeStyle = isDeleteMode
        ? '#f43f5e'
        : isRotateMode
          ? '#a3e635'
          : isBeingDragged
            ? '#fde047'
            : '#38bdf8';
      ctx.lineWidth = 2.4;
      ctx.beginPath();
      ctx.moveTo(c0.x, c0.y);
      ctx.lineTo(c1.x, c1.y);
      ctx.lineTo(c2.x, c2.y);
      ctx.lineTo(c3.x, c3.y);
      ctx.closePath();
      ctx.stroke();
    }

    if (item.kind === 'wall_ew') {
      const isGold = item.color === '#b45309';
      // Aligned cleanly on the North edge (gy + 0.0) so it never cuts into items inside tile (gx, gy)!
      this._drawIsoBox(
        ctx,
        gx,
        gy,
        1.0,
        0.16,
        isGold ? 28 : 24,
        isGold ? '#b45309' : '#cbd5e1',
        isGold ? '#78350f' : '#475569',
        isGold ? '#92400e' : '#64748b'
      );
      return;
    }

    if (item.kind === 'wall_ns') {
      const isGold = item.color === '#b45309';
      // Aligned cleanly on the West edge (gx + 0.0) so it never cuts into items inside tile (gx, gy)!
      this._drawIsoBox(
        ctx,
        gx,
        gy,
        0.16,
        1.0,
        isGold ? 28 : 24,
        isGold ? '#b45309' : '#cbd5e1',
        isGold ? '#78350f' : '#475569',
        isGold ? '#92400e' : '#64748b'
      );
      return;
    }

    if (item.kind === 'door') {
      this._drawIsoBox(ctx, gx + 0.1, gy + 0.1, 0.8, 0.8, 1.5, '#d97706', '#78350f', '#92400e');
      if (rot % 2 === 0) {
        this._drawIsoBox(ctx, gx + 0.05, gy + 0.02, 0.16, 0.22, 28, '#fbbf24', '#92400e', '#b45309');
        this._drawIsoBox(ctx, gx + 0.79, gy + 0.02, 0.16, 0.22, 28, '#fbbf24', '#92400e', '#b45309');
        this._drawIsoBox(ctx, gx + 0.05, gy, 0.9, 0.24, 4, '#fde047', '#b45309', '#d97706', 26);
      } else {
        this._drawIsoBox(ctx, gx + 0.02, gy + 0.05, 0.22, 0.16, 28, '#fbbf24', '#92400e', '#b45309');
        this._drawIsoBox(ctx, gx + 0.02, gy + 0.79, 0.22, 0.16, 28, '#fbbf24', '#92400e', '#b45309');
        this._drawIsoBox(ctx, gx, gy + 0.05, 0.24, 0.9, 4, '#fde047', '#b45309', '#d97706', 26);
      }
      return;
    }

    if (item.kind === 'chair') {
      this._drawIsoBox(ctx, gx + 0.22, gy + 0.22, 0.54, 0.54, 8, '#334155', '#1e293b', '#0f172a');
      if (rot === 0) {
        this._drawIsoBox(ctx, gx + 0.26, gy + 0.64, 0.46, 0.12, 12, '#475569', '#1e293b', '#0f172a', 8);
      } else if (rot === 1) {
        this._drawIsoBox(ctx, gx + 0.64, gy + 0.26, 0.12, 0.46, 12, '#475569', '#1e293b', '#0f172a', 8);
      } else if (rot === 2) {
        this._drawIsoBox(ctx, gx + 0.26, gy + 0.22, 0.46, 0.12, 12, '#475569', '#1e293b', '#0f172a', 8);
      } else {
        this._drawIsoBox(ctx, gx + 0.22, gy + 0.26, 0.12, 0.46, 12, '#475569', '#1e293b', '#0f172a', 8);
      }
      return;
    }

    if (item.kind === 'plant') {
      // Terracotta pot centered in tile so it never collides with edge walls
      this._drawIsoBox(ctx, gx + 0.3, gy + 0.3, 0.42, 0.42, 9, '#c2410c', '#7c2d12', '#9a3412');
      const p1 = this.gridToScreen(gx + 0.5, gy + 0.5, 14);
      const p2 = this.gridToScreen(gx + 0.43, gy + 0.55, 20);
      const p3 = this.gridToScreen(gx + 0.57, gy + 0.45, 19);
      const p4 = this.gridToScreen(gx + 0.5, gy + 0.5, 25);
      const s = this.scale;
      for (const [pt, rad, col] of [
        [p1, 8.5 * s, '#15803d'],
        [p2, 7.0 * s, '#16a34a'],
        [p3, 7.0 * s, '#22c55e'],
        [p4, 5.5 * s, '#4ade80'],
      ]) {
        ctx.fillStyle = col;
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, rad, 0, Math.PI * 2);
        ctx.fill();
      }
      return;
    }

    if (item.kind === 'desk') {
      const assignedAgent = this.agents.find((a) => a.id === item.assigned_agent_id);
      const isWorkingHere = assignedAgent && this.isAgentSeatedWorkingAtDesk(assignedAgent);
      const isBossDesk = item.assigned_agent_id === 'ramon';
      const vertical = rot % 2 === 1;
      const dw = vertical ? (isBossDesk ? 0.82 : 0.72) : (isBossDesk ? 1.45 : 1.2);
      const dd = vertical ? (isBossDesk ? 1.45 : 1.2) : (isBossDesk ? 0.82 : 0.72);

      // 1. Desk Table (rotates 90° on odd rotations)
      this._drawIsoBox(
        ctx,
        gx,
        gy,
        dw,
        dd,
        12,
        isBossDesk ? '#991b1b' : '#b45309',
        isBossDesk ? '#450a0a' : '#78350f',
        isBossDesk ? '#7f1d1d' : '#92400e'
      );

      // 2. Dual Computer Monitor & Keyboard (oriented by rot 0,1,2,3)
      const screenGlow = isWorkingHere
        ? (this.animTick % 14 < 7 ? '#22c55e' : '#38bdf8')
        : '#18181b';
      if (!vertical) {
        const monY = rot === 2 ? gy + 0.48 : gy + 0.12;
        const kbY = rot === 2 ? gy + 0.16 : gy + 0.38;
        const chairY = rot === 2 ? gy - 0.52 : gy + 0.78;
        this._drawIsoBox(ctx, gx + 0.22, monY, 0.68, 0.12, 11, '#475569', '#0f172a', screenGlow, 12);
        this._drawIsoBox(ctx, gx + 0.32, kbY, 0.45, 0.22, 1.5, '#cbd5e1', '#64748b', '#94a3b8', 12);
        this._drawIsoBox(ctx, gx + 0.34, chairY, 0.52, 0.48, 8, '#334155', '#1e293b', '#0f172a');
        if (!isWorkingHere) {
          const backY = rot === 2 ? chairY : chairY + 0.38;
          this._drawIsoBox(ctx, gx + 0.38, backY, 0.44, 0.1, 10, '#475569', '#1e293b', '#0f172a', 8);
        }
      } else {
        const monX = rot === 3 ? gx + 0.48 : gx + 0.12;
        const kbX = rot === 3 ? gx + 0.16 : gx + 0.38;
        const chairX = rot === 3 ? gx - 0.52 : gx + 0.78;
        this._drawIsoBox(ctx, monX, gy + 0.22, 0.12, 0.68, 11, '#475569', screenGlow, '#0f172a', 12);
        this._drawIsoBox(ctx, kbX, gy + 0.32, 0.22, 0.45, 1.5, '#cbd5e1', '#64748b', '#94a3b8', 12);
        this._drawIsoBox(ctx, chairX, gy + 0.34, 0.48, 0.52, 8, '#334155', '#1e293b', '#0f172a');
        if (!isWorkingHere) {
          const backX = rot === 3 ? chairX : chairX + 0.38;
          this._drawIsoBox(ctx, backX, gy + 0.38, 0.1, 0.44, 10, '#475569', '#1e293b', '#0f172a', 8);
        }
      }

      // 4. Spinning Star above desk
      const pulse = Math.sin(this.animTick * 0.08 + gx) * 3;
      const starPos = this.gridToScreen(gx + 0.55, gy + 0.3, 38 + pulse);
      this._drawStar(
        ctx,
        starPos.x,
        starPos.y,
        5,
        (isWorkingHere ? 10 : 7) * this.scale,
        (isWorkingHere ? 4.5 : 3) * this.scale,
        isWorkingHere ? '#22c55e' : item.color || '#facc15'
      );
      return;
    }

    if (item.kind === 'ph_flag') {
      const base = this.gridToScreen(gx + 0.5, gy + 0.5, 0);
      const top = this.gridToScreen(gx + 0.5, gy + 0.5, 42);
      ctx.strokeStyle = '#e4e4e7';
      ctx.lineWidth = 2.5 * this.scale;
      ctx.beginPath();
      ctx.moveTo(base.x, base.y);
      ctx.lineTo(top.x, top.y);
      ctx.stroke();

      const fw = 24 * this.scale;
      const fh = 14 * this.scale;
      ctx.fillStyle = '#0038a8';
      ctx.fillRect(top.x, top.y, fw, fh / 2);
      ctx.fillStyle = '#ce1126';
      ctx.fillRect(top.x, top.y + fh / 2, fw, fh / 2);
      ctx.fillStyle = '#ffffff';
      ctx.beginPath();
      ctx.moveTo(top.x, top.y);
      ctx.lineTo(top.x + fw * 0.42, top.y + fh / 2);
      ctx.lineTo(top.x, top.y + fh);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = '#fcd116';
      ctx.beginPath();
      ctx.arc(top.x + fw * 0.16, top.y + fh / 2, 2.3 * this.scale, 0, Math.PI * 2);
      ctx.fill();
      return;
    }

    if (item.kind === 'server_rack') {
      this._drawIsoBox(ctx, gx + 0.1, gy + 0.1, 0.8, 0.8, 32, '#1e293b', '#090d16', '#111827');
      const ledPos = this.gridToScreen(gx + 0.5, gy + 0.85, 22);
      ctx.fillStyle = this.animTick % 30 < 15 ? '#22c55e' : '#38bdf8';
      ctx.fillRect(ledPos.x - 4, ledPos.y, 4 * this.scale, 2 * this.scale);
      ctx.fillStyle = '#f43f5e';
      ctx.fillRect(ledPos.x + 2, ledPos.y + 4, 4 * this.scale, 2 * this.scale);
      return;
    }

    if (item.kind === 'water_cooler') {
      this._drawIsoBox(ctx, gx + 0.2, gy + 0.2, 0.6, 0.6, 18, '#0d9488', '#115e59', '#0f766e');
      this._drawIsoBox(ctx, gx + 0.3, gy + 0.3, 0.4, 0.4, 10, '#67e8f9', '#22d3ee', '#06b6d4', 18);
      return;
    }

    if (item.kind === 'war_table') {
      const center = this.gridToScreen(gx + 1, gy + 1, 10);
      ctx.fillStyle = '#92400e';
      ctx.beginPath();
      ctx.ellipse(center.x, center.y, 28 * this.scale, 15 * this.scale, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#b45309';
      ctx.lineWidth = 2;
      ctx.stroke();
      return;
    }

    if (item.kind === 'ping_pong') {
      const pw = rot % 2 === 1 ? 0.95 : 1.7;
      const pd = rot % 2 === 1 ? 1.7 : 0.95;
      this._drawIsoBox(ctx, gx, gy, pw, pd, 10, '#059669', '#065f46', '#047857');
      const n0 = rot % 2 === 1 ? this.gridToScreen(gx, gy + 0.85, 12) : this.gridToScreen(gx + 0.85, gy, 12);
      const n1 =
        rot % 2 === 1
          ? this.gridToScreen(gx + 0.95, gy + 0.85, 12)
          : this.gridToScreen(gx + 0.85, gy + 0.95, 12);
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      ctx.moveTo(n0.x, n0.y);
      ctx.lineTo(n1.x, n1.y);
      ctx.stroke();
      return;
    }

    if (item.kind === 'sofa') {
      const sw = rot % 2 === 1 ? 0.7 : 1.5;
      const sd = rot % 2 === 1 ? 1.5 : 0.7;
      this._drawIsoBox(ctx, gx, gy, sw, sd, 11, '#6366f1', '#4338ca', '#4f46e5');
      return;
    }

    if (item.kind === 'treadmill') {
      const tw = rot % 2 === 1 ? 0.55 : 0.9;
      const td = rot % 2 === 1 ? 0.9 : 0.55;
      this._drawIsoBox(ctx, gx, gy, tw, td, 6, '#334155', '#1e293b', '#0f172a');
      if (rot % 2 === 1) {
        this._drawIsoBox(ctx, gx, gy + 0.7, 0.55, 0.15, 20, '#94a3b8', '#475569', '#64748b');
      } else {
        this._drawIsoBox(ctx, gx + 0.7, gy, 0.15, 0.55, 20, '#94a3b8', '#475569', '#64748b');
      }
    }
  }

  _drawAgentAvatar(ctx, agent) {
    const isSelected = agent.id === this.selectedAgentId;
    const isSeatedWorking = this.isAgentSeatedWorkingAtDesk(agent);
    const wState = this.wanderState[agent.id] || { stepPhase: 0, isMoving: false, facing: 1 };
    const s = this.scale;

    const drawGx = isSeatedWorking ? agent.desk_x + 0.58 : agent.current_x + 0.5;
    const drawGy = isSeatedWorking ? agent.desk_y + 0.96 : agent.current_y + 0.5;

    const foot = this.gridToScreen(drawGx, drawGy, 0);
    const walkBob = (!isSeatedWorking && wState.isMoving)
      ? Math.abs(Math.sin(wState.stepPhase)) * 1.8
      : 0;
    const seatZ = isSeatedWorking ? 7 : walkBob;
    const bodyPos = this.gridToScreen(drawGx, drawGy, seatZ);

    ctx.fillStyle = isSelected ? 'rgba(163, 230, 53, 0.48)' : 'rgba(0, 0, 0, 0.32)';
    ctx.beginPath();
    ctx.ellipse(foot.x, foot.y, 12 * s, 6 * s, 0, 0, Math.PI * 2);
    ctx.fill();
    if (isSelected) {
      ctx.strokeStyle = '#a3e635';
      ctx.lineWidth = 1.8;
      ctx.stroke();
    }

    if (isSeatedWorking) {
      // SEATED IN CHAIR IN FRONT OF COMPUTER, TYPING ON KEYBOARD
      ctx.fillStyle = '#1e293b';
      ctx.fillRect(bodyPos.x - 7 * s, bodyPos.y - 5 * s, 10 * s, 4 * s);
      ctx.fillRect(bodyPos.x - 8 * s, bodyPos.y - 3 * s, 4 * s, 7 * s);

      ctx.fillStyle = agent.shirt_color || '#3b82f6';
      ctx.fillRect(bodyPos.x - 6 * s, bodyPos.y - 17 * s, 12 * s, 12 * s);

      const leftArmOffset = Math.sin(this.animTick * 0.65) * 2.4 * s;
      const rightArmOffset = Math.cos(this.animTick * 0.65) * 2.4 * s;
      ctx.fillStyle = agent.shirt_color || '#3b82f6';
      ctx.fillRect(bodyPos.x - 12 * s, bodyPos.y - 14 * s + leftArmOffset, 7 * s, 3.5 * s);
      ctx.fillRect(bodyPos.x - 10 * s, bodyPos.y - 11 * s + rightArmOffset, 7 * s, 3.5 * s);

      ctx.fillStyle = '#f5d0a9';
      ctx.fillRect(bodyPos.x - 14 * s, bodyPos.y - 14 * s + leftArmOffset, 3 * s, 3 * s);
      ctx.fillRect(bodyPos.x - 12 * s, bodyPos.y - 11 * s + rightArmOffset, 3 * s, 3 * s);

      ctx.fillStyle = '#1e293b';
      ctx.strokeStyle = '#475569';
      ctx.lineWidth = 1;
      ctx.fillRect(bodyPos.x + 3 * s, bodyPos.y - 19 * s, 5 * s, 14 * s);
      ctx.strokeRect(bodyPos.x + 3 * s, bodyPos.y - 19 * s, 5 * s, 14 * s);

      ctx.fillStyle = '#f5d0a9';
      ctx.fillRect(bodyPos.x - 6 * s, bodyPos.y - 28 * s, 11 * s, 11 * s);
      ctx.fillStyle = agent.hair_color || '#18181b';
      ctx.fillRect(bodyPos.x - 6 * s, bodyPos.y - 30 * s, 11 * s, 4 * s);
      ctx.fillRect(bodyPos.x + 1 * s, bodyPos.y - 28 * s, 4 * s, 8 * s);

      ctx.fillStyle = '#09090b';
      ctx.fillRect(bodyPos.x - 5 * s, bodyPos.y - 24 * s, 2 * s, 2 * s);
      ctx.fillRect(bodyPos.x - 1 * s, bodyPos.y - 24 * s, 2 * s, 2 * s);
    } else {
      // WALKING POSTURE
      const stride = wState.isMoving ? Math.sin(wState.stepPhase) : 0;
      const leftLegX = -4.5 * s + stride * 3.2 * s;
      const rightLegX = 1.0 * s - stride * 3.2 * s;
      const leftFootLift = stride > 0 ? -stride * 2.2 * s : 0;
      const rightFootLift = stride < 0 ? stride * 2.2 * s : 0;

      ctx.fillStyle = '#1e293b';
      ctx.fillRect(bodyPos.x + leftLegX, bodyPos.y - 10 * s + leftFootLift, 4 * s, 9 * s);
      ctx.fillRect(bodyPos.x + rightLegX, bodyPos.y - 10 * s + rightFootLift, 4 * s, 9 * s);

      ctx.fillStyle = '#09090b';
      ctx.fillRect(bodyPos.x + leftLegX - 0.5 * s, bodyPos.y - 2 * s + leftFootLift, 5 * s, 2.5 * s);
      ctx.fillRect(bodyPos.x + rightLegX - 0.5 * s, bodyPos.y - 2 * s + rightFootLift, 5 * s, 2.5 * s);

      const armSwing = stride * 3.5 * s;
      ctx.fillStyle = agent.shirt_color || '#3b82f6';
      ctx.fillRect(bodyPos.x - 9 * s, bodyPos.y - 21 * s - armSwing, 3 * s, 9 * s);

      ctx.fillStyle = agent.shirt_color || '#3b82f6';
      ctx.fillRect(bodyPos.x - 6.5 * s, bodyPos.y - 22 * s, 13 * s, 12 * s);

      ctx.fillStyle = agent.shirt_color || '#3b82f6';
      ctx.fillRect(bodyPos.x + 6 * s, bodyPos.y - 21 * s + armSwing, 3 * s, 9 * s);
      ctx.fillStyle = '#f5d0a9';
      ctx.fillRect(bodyPos.x + 6 * s, bodyPos.y - 13 * s + armSwing, 3 * s, 2.5 * s);

      ctx.fillStyle = '#f5d0a9';
      ctx.fillRect(bodyPos.x - 6 * s, bodyPos.y - 33 * s, 12 * s, 11 * s);
      ctx.fillStyle = agent.hair_color || '#18181b';
      ctx.fillRect(bodyPos.x - 6 * s, bodyPos.y - 35 * s, 12 * s, 4 * s);

      const eyeOffset = wState.facing > 0 ? 1 * s : -1 * s;
      ctx.fillStyle = '#09090b';
      ctx.fillRect(bodyPos.x - 3 * s + eyeOffset, bodyPos.y - 29 * s, 2 * s, 2 * s);
      ctx.fillRect(bodyPos.x + 2 * s + eyeOffset, bodyPos.y - 29 * s, 2 * s, 2 * s);
    }

    const labelY = bodyPos.y - (isSeatedWorking ? 38 : 44) * s;
    const tagText = isSeatedWorking
      ? `${agent.name.toUpperCase()} 💻 WORKING`
      : `${agent.name.toUpperCase()}`;
    ctx.font = `bold ${Math.max(9, Math.round(10 * s))}px monospace`;
    const tw = ctx.measureText(tagText).width + 14 * s;

    ctx.fillStyle = isSeatedWorking
      ? '#15803d'
      : agent.is_hive_lead
        ? '#dc2626'
        : 'rgba(20, 20, 25, 0.92)';
    ctx.strokeStyle = isSelected ? '#a3e635' : '#52525b';
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.roundRect(bodyPos.x - tw / 2, labelY - 12 * s, tw, 15 * s, 3 * s);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'center';
    ctx.fillText(tagText, bodyPos.x, labelY - 1 * s);

    if (agent.speech_bubble) {
      const bubbleY = labelY - 27 * s;
      const isSweldo = agent.speech_bubble.toUpperCase().includes('SWELDO');
      ctx.font = `bold ${Math.max(10, Math.round((isSweldo ? 12 : 10) * s))}px sans-serif`;
      const bw = ctx.measureText(agent.speech_bubble).width + 18 * s;
      const bh = (isSweldo ? 22 : 17) * s;

      ctx.fillStyle = isSweldo ? '#1e3a8a' : 'rgba(15, 23, 42, 0.94)';
      ctx.strokeStyle = isSweldo ? '#60a5fa' : '#38bdf8';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.roundRect(bodyPos.x - bw / 2, bubbleY - bh / 2, bw, bh, 5 * s);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = isSweldo ? '#fde047' : '#e0f2fe';
      ctx.fillText(agent.speech_bubble, bodyPos.x, bubbleY + 4 * s);
    }
    ctx.textAlign = 'start';
  }

  _drawCollaborationBeams(ctx, floorAgents) {
    for (const sender of floorAgents) {
      if (!sender.collaborating_with) continue;
      const target = floorAgents.find((a) => a.id === sender.collaborating_with);
      if (!target) continue;

      const p1 = this.gridToScreen(sender.current_x + 0.5, sender.current_y + 0.8, 20);
      const p2 = this.gridToScreen(target.current_x + 0.5, target.current_y + 0.8, 20);

      ctx.save();
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      ctx.lineDashOffset = -this.animTick * 0.6;
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();
      ctx.restore();
    }
  }

  _drawStar(ctx, cx, cy, spikes, outerRadius, innerRadius, color) {
    let rot = (Math.PI / 2) * 3 + this.animTick * 0.03;
    let x = cx;
    let y = cy;
    const step = Math.PI / spikes;

    ctx.beginPath();
    ctx.moveTo(cx, cy - outerRadius);
    for (let i = 0; i < spikes; i++) {
      x = cx + Math.cos(rot) * outerRadius;
      y = cy + Math.sin(rot) * outerRadius;
      ctx.lineTo(x, y);
      rot += step;

      x = cx + Math.cos(rot) * innerRadius;
      y = cy + Math.sin(rot) * innerRadius;
      ctx.lineTo(x, y);
      rot += step;
    }
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = 'rgba(255,255,255,0.7)';
    ctx.lineWidth = 1;
    ctx.stroke();
  }
}

window.IsometricOfficeEngine = IsometricOfficeEngine;
