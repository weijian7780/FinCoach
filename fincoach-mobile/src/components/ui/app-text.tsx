import { type Ref } from 'react';
import { Text, type TextProps, TextInput, type TextInputProps } from 'react-native';

// Drop-in replacements for Text / TextInput that pin text to the design size,
// ignoring the device's font-size accessibility setting. RN 0.85 / React 19 no
// longer honors Text.defaultProps, so a wrapper is the reliable way to lock it.
export function AppText(props: TextProps) {
  return <Text {...props} allowFontScaling={false} />;
}

// ref is a plain prop in React 19; forwarding it lets callers focus the input.
export function AppTextInput({ ref, ...props }: TextInputProps & { ref?: Ref<TextInput> }) {
  return <TextInput ref={ref} {...props} allowFontScaling={false} />;
}
