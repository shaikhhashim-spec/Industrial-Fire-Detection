/* Ambient module declarations for offline IDE type checking when node_modules is not installed */

declare module "react" {
  export const lazy: any;
  export const Suspense: any;
  export const useMemo: any;
  export const useState: any;
  export const useEffect: any;
  export const useCallback: any;
  export const useRef: any;
  export type ChangeEvent<T = any> = { target: { value: string; checked: boolean } };
  export type ReactNode = any;
  export type FC<P = any> = (props: P) => any;
  const React: any;
  export default React;
}

declare module "react/jsx-runtime" {
  export const jsx: any;
  export const jsxs: any;
  export const Fragment: any;
}

declare module "three" {
  export class Vector2 {
    x: number;
    y: number;
    constructor(x?: number, y?: number);
  }
  export class Vector3 {
    x: number;
    y: number;
    z: number;
    constructor(x?: number, y?: number, z?: number);
    clone(): Vector3;
    normalize(): Vector3;
  }
  export class Quaternion {
    setFromUnitVectors(vFrom: Vector3, vTo: Vector3): this;
  }
  export class Color {
    constructor(color?: any);
  }
  export class Mesh {
    position: Vector3;
    rotation: any;
    scale: any;
    material: any;
    constructor(geo?: any, mat?: any);
  }
  export class Group {
    position: Vector3;
    quaternion: Quaternion;
    children: any[];
    rotation: any;
    scale: any;
    userData: any;
    add(child: any): this;
    remove(child: any): this;
  }
  export class Texture {
    colorSpace: any;
    anisotropy: number;
  }
  export class Clock {
    elapsedTime: number;
    getElapsedTime(): number;
    getDelta(): number;
  }
  export class ShaderMaterial {
    constructor(params?: any);
  }
  export class SphereGeometry {
    constructor(...args: any[]);
  }
  export class CylinderGeometry {
    constructor(...args: any[]);
  }
  export class RingGeometry {
    constructor(...args: any[]);
  }
  export const DoubleSide: any;
  export const BackSide: any;
  export const FrontSide: any;
  export const AdditiveBlending: any;
  export const SRGBColorSpace: any;
  export const ACESFilmicToneMapping: any;
  const THREE: any;
  export default THREE;
}

declare module "@react-three/fiber" {
  export function useFrame(callback: (state: any, delta: number) => void): void;
  export const Canvas: any;
  export type ThreeElements = Record<string, any>;
}

declare module "@react-three/drei" {
  export const OrbitControls: any;
  export const Stars: any;
  export function useTexture(urls: any): any;
}

declare module "@tanstack/react-router" {
  export function createFileRoute(path: string): any;
  export function createRouter(options: any): any;
  export const RouterProvider: any;
  export const Link: any;
  export const Outlet: any;
}
