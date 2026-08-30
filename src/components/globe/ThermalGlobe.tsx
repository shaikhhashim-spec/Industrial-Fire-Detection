import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stars } from "@react-three/drei";
import { Suspense, useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Graticule } from "./Coastlines";
import { Markers } from "./Markers";
import { Earth, Atmosphere } from "./Earth";
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
    <Canvas camera={{ position: [0, 1.6, 5.2], fov: 45 }} dpr={[1, 2]}>
      <color attach="background" args={["#080a0c"]} />
      <ambientLight intensity={0.55} />
      <directionalLight position={[5, 3, 5]} intensity={1.1} color="#bcd6ea" />
      <directionalLight position={[-6, -2, -4]} intensity={0.35} color="#e08a52" />
      <Stars radius={60} depth={30} count={1800} factor={3} fade speed={0.4} />
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
        minDistance={3}
        maxDistance={9}
        rotateSpeed={0.5}
        zoomSpeed={0.6}
      />
    </Canvas>
  );
}
