import { useMemo, useState, useRef, useEffect } from "react";
import { Canvas } from "@react-three/fiber";
import { CameraControls, Instances, Instance, PerspectiveCamera, ContactShadows, Float, Html } from "@react-three/drei";
import * as THREE from "three";
import type { MaterialItem } from "../types";
import { parseStorageBin } from "../types";

interface Props {
  materials: MaterialItem[];
  highlightedBins: Set<string>;
  selectedBins: Set<string>;
  onBinClick: (bin: string) => void;
  activeFloor: number;
}

const ROWS = 6;
const GROUPS_PER_ROW = 4;
const LEVELS = 4;
const MAX_CELLS = 9;

const SHELF_WIDTH = 3.2;
const SHELF_DEPTH = 0.8;
const SHELF_HEIGHT = 2.4;
const PILLAR_SIZE = 0.1;
const BOARD_THICKNESS = 0.025;
const BOX_SIZE = [0.32, 0.18, 0.38] as [number, number, number];

const ROOM_SIZE = { W: 42, D: 42, H: 12 };

const COLORS = {
  PILLAR: "#9ca3af",
  BEAM: "#6b7280",
  BOARD: "#f8fafc",
  BOX_NORMAL: "#3b82f6",
  BOX_HIGHLIGHT: "#fbbf24",
  BOX_SELECTED: "#06b6d4",
  BOX_BLACK: "#1e293b",
  FLOOR: "#ffffff",
  WALL: "#f1f5f9",
  SKY: "#ffffff",
  GRID: "#e5e7eb",
};

function ViewFocusNode({ position, onFocus }: { position: [number, number, number], onFocus: () => void }) {
  const [hovered, setHovered] = useState(false);
  return (
    <group position={position}>
      <Float speed={2} rotationIntensity={0.5} floatIntensity={0.5}>
        <mesh 
          onPointerOver={() => { setHovered(true); document.body.style.cursor = "pointer"; }}
          onPointerOut={() => { setHovered(false); document.body.style.cursor = "auto"; }}
          onClick={(e) => { e.stopPropagation(); onFocus(); }}
        >
          <sphereGeometry args={[0.18, 16, 16]} />
          <meshStandardMaterial 
            color={hovered ? "#60a5fa" : "#3b82f6"} 
            emissive={hovered ? "#60a5fa" : "#3b82f6"} 
            emissiveIntensity={0.6} 
            transparent 
            opacity={0.7} 
          />
        </mesh>
      </Float>
      {hovered && (
        <Html position={[0, 0.5, 0]} center>
          <div className="bg-white/90 text-[#2C3E50] text-[10px] px-3 py-1.5 rounded-lg whitespace-nowrap backdrop-blur-md shadow-md border border-zinc-200/50 font-medium">
            查看该货架
          </div>
        </Html>
      )}
    </group>
  );
}

function StorageBoxMesh({ 
  position, 
  binKey, 
  isHighlighted, 
  isSelected, 
  hasMaterials,
  onClick,
  isBlackBox = false
}: { 
  position: [number, number, number], 
  binKey: string,
  isHighlighted: boolean,
  isSelected: boolean,
  hasMaterials: boolean,
  onClick: (bin: string) => void,
  isBlackBox?: boolean
}) {
  const [hovered, setHovered] = useState(false);

  const color = useMemo(() => {
    if (isBlackBox && isSelected) return "#06b6d4";
    if (isSelected) return COLORS.BOX_SELECTED;
    if (isHighlighted) return COLORS.BOX_HIGHLIGHT;
    if (hovered) return "#60a5fa";
    if (isBlackBox) return COLORS.BOX_BLACK;
    if (hasMaterials) return "#2563eb";
    return COLORS.BOX_NORMAL;
  }, [isHighlighted, isSelected, hovered, isBlackBox, hasMaterials]);

  const innerColor = useMemo(() => {
    if (isBlackBox) return "#334155";
    if (hasMaterials) return "#1e40af";
    return "#1d4ed8";
  }, [isBlackBox, hasMaterials]);

  return (
    <group position={position} rotation={[0, -Math.PI / 2, 0]}>
      {isSelected && (
        <mesh>
          <boxGeometry args={[BOX_SIZE[0] + 0.08, BOX_SIZE[1] + 0.08, BOX_SIZE[2] + 0.08]} />
          <meshBasicMaterial color={COLORS.BOX_SELECTED} transparent opacity={0.4} side={THREE.BackSide} />
        </mesh>
      )}

      <mesh
        onClick={(e) => { e.stopPropagation(); onClick(binKey); }}
        onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = "pointer"; }}
        onPointerOut={() => { setHovered(false); document.body.style.cursor = "auto"; }}
      >
        <boxGeometry args={BOX_SIZE} />
        <meshStandardMaterial color={color} roughness={0.5} metalness={0.1} />
      </mesh>

      <mesh position={[0, 0.001, 0]}>
        <boxGeometry args={[BOX_SIZE[0] - 0.02, 0.001, BOX_SIZE[2] - 0.02]} />
        <meshStandardMaterial color={innerColor} roughness={0.7} transparent opacity={0.6} />
      </mesh>

      <mesh position={[BOX_SIZE[2]/2 + 0.015, -BOX_SIZE[1]/6, 0]} rotation={[0, Math.PI/2, 0]}>
        <planeGeometry args={[0.08, 0.05]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={0.9} />
      </mesh>
    </group>
  );
}

function ShelfBeam({ position, isLong }: { position: [number, number, number], isLong: boolean }) {
  return (
    <mesh position={position} castShadow>
      <boxGeometry args={[isLong ? SHELF_WIDTH + 0.15 : 0.06, 0.06, 0.04]} />
      <meshStandardMaterial color={COLORS.BEAM} roughness={0.4} metalness={0.5} />
    </mesh>
  );
}

function WarehouseRoom({ width, depth, height }: { width: number, depth: number, height: number }) {
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]} receiveShadow>
        <planeGeometry args={[width, depth]} />
        <meshStandardMaterial color={COLORS.FLOOR} roughness={0.95} metalness={0.02} />
      </mesh>
      
      <mesh position={[0, height / 2, -depth / 2]} receiveShadow>
        <boxGeometry args={[width, height, 0.15]} />
        <meshStandardMaterial color={COLORS.WALL} roughness={0.9} />
      </mesh>
      <mesh position={[0, height / 2, depth / 2]} receiveShadow>
        <boxGeometry args={[width, height, 0.15]} />
        <meshStandardMaterial color={COLORS.WALL} roughness={0.9} />
      </mesh>
      <mesh position={[width / 2, height / 2, 0]} receiveShadow>
        <boxGeometry args={[0.15, height, depth]} />
        <meshStandardMaterial color={COLORS.WALL} roughness={0.9} />
      </mesh>
      <group position={[-width / 2, height / 2, 0]}>
        <mesh position={[0, 0, depth / 3]} receiveShadow>
          <boxGeometry args={[0.15, height, depth / 3]} />
          <meshStandardMaterial color={COLORS.WALL} roughness={0.9} />
        </mesh>
        <mesh position={[0, 0, -depth / 3]} receiveShadow>
          <boxGeometry args={[0.15, height, depth / 3]} />
          <meshStandardMaterial color={COLORS.WALL} roughness={0.9} />
        </mesh>
        <mesh position={[0, height / 3 + height / 6, 0]} receiveShadow>
          <boxGeometry args={[0.15, height / 3, depth / 3]} />
          <meshStandardMaterial color={COLORS.WALL} roughness={0.9} />
        </mesh>
        <mesh position={[0, -height / 6, 0]}>
          <boxGeometry args={[0.25, (height * 2) / 3, depth / 3 - 0.3]} />
          <meshStandardMaterial color="#475569" metalness={0.6} roughness={0.4} />
        </mesh>
      </group>
    </group>
  );
}

export default function WarehouseScene({
  materials,
  highlightedBins,
  selectedBins,
  onBinClick,
  activeFloor,
}: Props) {
  const cameraControlsRef = useRef<CameraControls>(null!);

  const pillarGeo = useMemo(() => new THREE.BoxGeometry(PILLAR_SIZE, SHELF_HEIGHT, PILLAR_SIZE), []);
  const boardGeo = useMemo(() => new THREE.BoxGeometry(SHELF_WIDTH + 0.05, BOARD_THICKNESS, SHELF_DEPTH - 0.05), []);

  const materialsInCells = useMemo(() => {
    const map = new Map<string, boolean>();
    materials.forEach((m) => {
      if (!m.storage_bin) return;
      const pos = parseStorageBin(m.storage_bin);
      if (!pos || pos.floor !== activeFloor) return;
      map.set(`${pos.group}-${pos.level}-${pos.cell}`, true);
    });
    return map;
  }, [materials, activeFloor]);

  const { shelfData, allCells, groupNodes } = useMemo(() => {
    const pillars: { pos: [number, number, number] }[] = [];
    const boards: { pos: [number, number, number] }[] = [];
    const beams: { pos: [number, number, number], isLong: boolean }[] = [];
    const cells: { binKey: string, pos: [number, number, number], isBlackBox?: boolean }[] = [];
    const nodes: { pos: [number, number, number], target: [number, number, number] }[] = [];

    const pX = SHELF_WIDTH / 2 - PILLAR_SIZE / 2;
    const pZ = SHELF_DEPTH / 2 - PILLAR_SIZE / 2;

    for (let r = 1; r <= ROWS; r++) {
      const isR2 = (r - 1) % 2;
      const rowZ = Math.floor((r - 1) / 2) * 5.5 - (ROWS * 2.75) / 2 + (isR2 === 0 ? -0.45 : 0.45);

      for (let g = 1; g <= GROUPS_PER_ROW; g++) {
        const groupX = (g - 1) * (SHELF_WIDTH + 0.8) - (GROUPS_PER_ROW * SHELF_WIDTH) / 2;
        const gIdx = (activeFloor - 1) * ROWS * GROUPS_PER_ROW + (r - 1) * GROUPS_PER_ROW + g;
        
        nodes.push({ 
          pos: [groupX + SHELF_WIDTH + 1.5, 1.8, rowZ], 
          target: [groupX, 1.2, rowZ] 
        });
        
        [[-1, -1], [-1, 1], [1, -1], [1, 1]].forEach(([mx, mz]) => {
          pillars.push({ pos: [groupX + mx * pX, SHELF_HEIGHT / 2, rowZ + mz * pZ] });
        });

        for (let i = 0; i < LEVELS; i++) {
          const y = i * (SHELF_HEIGHT / LEVELS);
          boards.push({ pos: [groupX, y + 0.012, rowZ] });
          beams.push({ pos: [groupX, y + 0.04, rowZ + (isR2 === 0 ? SHELF_DEPTH/2 : -SHELF_DEPTH/2)], isLong: true });
        }

        for (let l = 1; l <= LEVELS; l++) {
          for (let c = 1; c <= MAX_CELLS; c++) {
            const cellW = (SHELF_WIDTH - 2 * PILLAR_SIZE) / MAX_CELLS;
            const x = groupX - SHELF_WIDTH / 2 + PILLAR_SIZE + (c - 0.5) * cellW;
            const y = (l - 1) * (SHELF_HEIGHT / LEVELS) + BOARD_THICKNESS + BOX_SIZE[1] / 2 + 0.05;
            
            const isBlackBox = gIdx === 4 && l === 2 && c === 5;
            cells.push({ binKey: `${gIdx}-${l}-${c}`, pos: [x, y, rowZ], isBlackBox });
          }
        }
      }
    }
    return { shelfData: { pillars, boards, beams }, allCells: cells, groupNodes: nodes };
  }, [activeFloor]);

  useEffect(() => {
    if (cameraControlsRef.current) {
      const box = new THREE.Box3(
        new THREE.Vector3(-ROOM_SIZE.W/2 + 2, 0, -ROOM_SIZE.D/2 + 2),
        new THREE.Vector3(ROOM_SIZE.W/2 - 2, ROOM_SIZE.H - 2, ROOM_SIZE.D/2 - 2)
      );
      cameraControlsRef.current.setBoundary(box);
    }
  }, []);

  return (
    <div className="w-full h-full relative bg-[#ffffff]">
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 flex gap-2">
        <div className="px-4 py-2 bg-white/80 backdrop-blur-xl border border-zinc-200/50 rounded-full text-xs text-[#34495E] shadow-sm font-medium">
          💡 点击地面的蓝球可快速定位每个货架视角
        </div>
      </div>

      <Canvas dpr={[1, 1.5]} shadows gl={{ antialias: true }}>
        <color attach="background" args={["#ffffff"]} />
        <PerspectiveCamera makeDefault position={[32, 20, 32]} />
        <CameraControls 
          ref={cameraControlsRef} 
          minDistance={2} 
          maxDistance={40} 
          makeDefault 
          smoothTime={0.4}
        />

        <ambientLight intensity={1.8} />
        <directionalLight 
          position={[15, 25, 10]} 
          intensity={1.2} 
          castShadow
          shadow-mapSize-width={1024}
          shadow-mapSize-height={1024}
          shadow-camera-far={80}
          shadow-camera-left={-30}
          shadow-camera-right={30}
          shadow-camera-top={30}
          shadow-camera-bottom={-30}
        />
        <pointLight position={[-10, 18, -10]} intensity={0.5} color="#e0e7ff" />

        <WarehouseRoom width={ROOM_SIZE.W} depth={ROOM_SIZE.D} height={ROOM_SIZE.H} />

        {groupNodes.map((n, i) => (
          <ViewFocusNode 
            key={i} 
            position={n.pos} 
            onFocus={() => {
              const camPos = n.pos.map((v, i) => i === 1 ? 5.5 : v) as [number, number, number];
              cameraControlsRef.current?.setLookAt(...camPos, n.target[0], n.target[1], n.target[2], true);
            }} 
          />
        ))}

        <Instances geometry={pillarGeo}>
          <meshStandardMaterial color={COLORS.PILLAR} roughness={0.3} metalness={0.7} />
          {shelfData.pillars.map((p, i) => (
            <Instance key={i} position={p.pos} />
          ))}
        </Instances>

        <Instances geometry={boardGeo}>
          <meshStandardMaterial color={COLORS.BOARD} roughness={0.85} metalness={0.05} />
          {shelfData.boards.map((b, i) => (
            <Instance key={i} position={b.pos} />
          ))}
        </Instances>

        {shelfData.beams.map((b, i) => (
          <ShelfBeam key={i} position={b.pos} isLong={b.isLong} />
        ))}

        {allCells.map((cell) => (
          <StorageBoxMesh
            key={cell.binKey}
            binKey={cell.binKey}
            position={cell.pos}
            isHighlighted={highlightedBins.has(cell.binKey)}
            isSelected={selectedBins.has(cell.binKey)}
            hasMaterials={materialsInCells.has(cell.binKey)}
            onClick={onBinClick}
            isBlackBox={cell.isBlackBox}
          />
        ))}

        <ContactShadows 
          position={[0, -0.01, 0]} 
          opacity={0.12} 
          scale={60} 
          blur={2.5} 
          far={15}
          color="#94a3b8"
        />
      </Canvas>
    </div>
  );
}
