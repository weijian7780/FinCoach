import { Text, type TextProps, TextInput, type TextInputProps } from 'react-native';

// Drop-in replacements for Text / TextInput that pin text to the design size,
// ignoring the device's font-size accessibility setting. RN 0.85 / React 19 no
// longer honors Text.defaultProps, so a wrapper is the reliable way to lock it.
export function AppText(props: TextProps) {
  return <Text {...props} allowFontScaling={false} />;
}

export function AppTextInput(props: TextInputProps) {
  return <TextInput {...props} allowFontScaling={false} />;
}
