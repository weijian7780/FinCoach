import type { PropsWithChildren } from 'react';
import { View } from 'react-native';

type ProgressRingProps = PropsWithChildren<{
  color: string;
  progress: number;
  size?: number;
  strokeWidth?: number;
}>;

export function ProgressRing({ children, color, progress, size = 140, strokeWidth = 11 }: ProgressRingProps) {
  const boundedProgress = Math.min(1, Math.max(0, progress));
  const segmentCount = 40;
  const activeSegments = Math.round(boundedProgress * segmentCount);
  const segmentWidth = Math.max(3, strokeWidth * 0.34);
  const radius = (size - strokeWidth) / 2;
  const center = size / 2;

  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      {Array.from({ length: segmentCount }, (_, index) => {
        const angle = (index / segmentCount) * Math.PI * 2 - Math.PI / 2;
        const left = center + radius * Math.cos(angle) - segmentWidth / 2;
        const top = center + radius * Math.sin(angle) - strokeWidth / 2;
        return (
          <View
            key={index}
            style={{
              position: 'absolute',
              left,
              top,
              width: segmentWidth,
              height: strokeWidth,
              borderRadius: segmentWidth,
              backgroundColor: index < activeSegments ? color : '#e9e6f3',
              transform: [{ rotate: `${angle + Math.PI / 2}rad` }],
            }}
          />
        );
      })}
      <View style={{ alignItems: 'center', justifyContent: 'center' }}>{children}</View>
    </View>
  );
}
