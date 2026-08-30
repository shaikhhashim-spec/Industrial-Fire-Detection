import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stars } from "@react-three/drei";
import { useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Coastlines, Graticule } from "./Coastlines";
import { Markers } from "./Markers";
import { latLonToVec3, type ThermalEvent } from "@/lib/thermal";

function Atmosphere() {
  return (
    <mesh scale={1.14}>
      <sphereGeometry args={[2, 48, 48]} />
      <meshBasicMaterial
        color="#2f6f9e"
        transparent
        opacity={0.12}
        side={THREE.BackSide}
        depthWrite={false}
      />
    </mesh>
  );
}

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
  const target = useRef(new THREE.Vector3(...latLonToVec3(22, 80, 1)));

  useFrame((_, delta) => {
    const g = world.current;
    if (!g) return;
    const dt = Math.min(delta, 0.05);
    if (spin) g.rotation.y += dt * 0.06;
    else {
      // ease the focus region toward the camera when auto-rotate is off
      const desired = -Math.atan2(target.current.z, -target.current.x) - Math.PI / 2;
      g.rotation.y += (desired - g.rotation.y) * (1 - Math.exp(-1.6 * dt));
    }
  });

  return (
    <group ref={world}>
      <mesh>
        <sphereGeometry args={[2, 64, 64]} />
        <meshStandardMaterial
          color="#0e1620"
          roughness={0.95}
          metalness={0.05}
          emissive="#08131c"
          emissiveIntensity={0.6}
        />
      </mesh>
      <Graticule />
      <Coastlines />
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
