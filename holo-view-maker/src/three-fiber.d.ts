// Global JSX augmentation for React Three Fiber & standard HTML elements
declare global {
  namespace React {
    namespace JSX {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      interface IntrinsicElements {
        [elemName: string]: any;
      }
    }
  }
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    interface IntrinsicElements {
      [elemName: string]: any;
    }
  }
}

export {};
