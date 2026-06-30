import { View } from 'react-native';

// Approximates the Stitch mockups' soft top gradient (indigo fading into the
// surface) by stacking translucent slices. Avoids pulling in the native
// expo-linear-gradient module, so no dev build rebuild is required.
export function AuthBackdrop({
  color,
  height,
  maxOpacity = 0.5,
}: {
  color: string;
  height: number;
  maxOpacity?: number;
}) {
  const slices = 16;
  return (
    <View pointerEvents="none" style={{ position: 'absolute', top: 0, left: 0, right: 0, height }}>
      {Array.from({ length: slices }).map((_, index) => (
        <View
          key={index}
          style={{ flex: 1, backgroundColor: color, opacity: maxOpacity * (1 - index / slices) }}
        />
      ))}
    </View>
  );
}
