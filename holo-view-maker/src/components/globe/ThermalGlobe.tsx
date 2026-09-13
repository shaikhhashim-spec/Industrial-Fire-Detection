import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stars } from "@react-three/drei";
import { Suspense, useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Graticule } from "./Coastlines";
import { Markers } from "./Markers";
import { Earth, Atmosphere, SUN_DIRECTION } from "./Earth";
import { type ThermalEvent } from "@/lib/thermal";

/** Rotation that brings ~80E to face the camera. */
const FOCUS_ROTATION = ((80 + 180) * Math.PI) / 180 - Math.PI / 2;

function Scene({
  events,
  selectedId,
  colorBy,
  spin,
  onSelect,
}: {
  events: ThermalEvent[];
  selectedId: string | null;
  colorBy: "category" | "risk";
  spin: boolean;
  onSelect: (id: string) => void;
}) {
  const world = useRef<THREE.Group>(null);

  useFrame((_, delta) => {
    const g = world.current;
    if (!g || !spin) return;
    g.rotation.y += Math.min(delta, 0.05) * 0.05;
  });

  // Start with the South-Asian thermal corridor facing the camera.
  return (
    <group ref={world} rotation-y={FOCUS_ROTATION}>
      <Suspense fallback={null}>
        <Earth />
      </Suspense>
      <Graticule />
      <Markers events={events} selectedId={selectedId} colorBy={colorBy} onSelect={onSelect} />
    </group>
  );
}


export function ThermalGlobe({
  events,
  selectedId,
  colorBy,
  spin,
  onSelect,
}: {
  events: ThermalEvent[];
  selectedId: string | null;
  colorBy: "category" | "risk";
  spin: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <Canvas
      camera={{ position: [0, 1.6, 5.2], fov: 45 }}
      dpr={[1, 2]}
      gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.05 }}
    >
      <color attach="background" args={["#04060a"]} />
      <ambientLight intensity={0.045} />
      {/* sun */}
      <directionalLight
        position={SUN_DIRECTION.clone().multiplyScalar(6)}
        intensity={3.1}
        color="#fff4e2"
      />
      {/* faint bounce so the night side isn't pure black */}
      <directionalLight position={[-6, -2, -4]} intensity={0.12} color="#3f6d9c" />
      <Stars radius={80} depth={40} count={3000} factor={3} fade speed={0.3} />
      <Atmosphere />

      <Scene
        events={events}
        selectedId={selectedId}
        colorBy={colorBy}
        spin={spin}
        onSelect={onSelect}
      />
      <OrbitControls
        enablePan={false}
        minDistance={2.012}
        maxDistance={14}
        rotateSpeed={0.5}
        zoomSpeed={0.8}
      />
    </Canvas>
  );
}
