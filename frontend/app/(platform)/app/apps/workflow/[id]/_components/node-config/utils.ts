// 验证变量名格式（只允许字母、数字、下划线，且不能以数字开头）
export const isValidVariableName = (name: string): boolean => {
  return /^[a-zA-Z_][a-zA-Z0-9_]*$/.test(name)
}

// 根据参数类型确定显示的类型名
export const getTypeName = (type: string): string => {
  switch (type) {
    case 'number': return 'Number'
    case 'checkbox': return 'Boolean'
    case 'array': return 'Array'
    case 'object': return 'Object'
    case 'file': return 'File'
    case 'image': return 'Image'
    case 'files': return 'Files'
    case 'images': return 'Images'
    default: return 'String'
  }
}

// 根据循环变量类型获取显示类型名
export const getLoopVarTypeName = (type: string): string => {
  switch (type) {
    case 'number': return 'Number'
    case 'boolean': return 'Boolean'
    case 'array': return 'Array'
    case 'object': return 'Object'
    default: return 'String'
  }
}
