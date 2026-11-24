/**
 * passwordPolicy.ts — Единый источник правил сложности пароля на фронтенде (Правило №6).
 * Полностью синхронизирован с backend/app/services/password_policy.py.
 */

export const MIN_PASSWORD_LENGTH = 8

export const COMMON_PASSWORDS = new Set([
  '123456', '12345678', '123456789', '1234567890', '12345',
  'qwerty', 'password', '111111', '11111111', '123123',
  'abc123', 'qwerty123', '1q2w3e4r', 'йцукен', 'qwertyuiop',
  '1234567', '000000', 'iloveyou', 'admin', 'admin123',
  'letmein', 'welcome', 'monkey', 'dragon', 'football',
  'baseball', 'master', 'superman', 'trustno1', 'sunshine',
  'princess', 'qwe123', 'password1', 'password123', 'passw0rd',
  '1qaz2wsx', 'zaq12wsx', 'qazwsx', 'qweasd', 'asdfgh',
  'asdasd', '123qwe', 'qwerty1', 'qwerty12', '1234',
  '12345678910', '0000000', '123321', '654321', '7777777',
  '1111111', '88888888', '121212', '222222', 'aaaaaa',
  '1q2w3e', '1qazxsw2', 'zxcvbnm', 'zxcvbn', 'a123456',
  'fuckyou', 'whatever', '123456a', '666666', 'qazwsxedc',
  'pokemon', 'qwerty12345', 'qwertyui', 'starwars', 'login',
  'qweqwe', '123123123', 'aa123456', 'qwerty123456', 'parol',
  'parol123', 'qwer1234', '123abc', '1234qwer', 'lolkek',
  'guest', 'test', 'test123', 'user123', 'temp1234',
  'changeme', 'default1', 'root1234', 'pass1234', 'pass123',
  'secret12', 'iloveyou1', 'hello123', 'flower1', 'sunshine1',
  'shadow12', 'mustang1', 'access12', 'batman12', 'nikita123',
  'sergey123', 'maxim123', 'vladimir1', 'andrey123', 'oleg1234',
  '1234561', 'zxcasdqwe', 'q1w2e3r4', 'p@ssw0rd', 'p@ssword',
])

export interface PasswordEvaluation {
  currentLength: number
  minLength: number
  hasMinLength: boolean
  hasLetter: boolean
  hasDigit: boolean
  isCommon: boolean
  matchesIdentifier: boolean
  isValid: boolean
  errorMessage: string | null
}

export function evaluatePassword(
  password: string | null | undefined,
  identifiers: (string | null | undefined)[] = [],
): PasswordEvaluation {
  const pw = password || ''
  const currentLength = pw.length
  const minLength = MIN_PASSWORD_LENGTH
  const hasMinLength = currentLength >= minLength
  const hasLetter = /[a-zA-Zа-яА-ЯёЁ]/.test(pw)
  const hasDigit = /\d/.test(pw)

  const norm = pw.trim().toLowerCase()
  const isCommon = COMMON_PASSWORDS.has(norm)

  let matchesIdentifier = false
  for (const ident of identifiers) {
    if (ident && norm && norm === ident.trim().toLowerCase()) {
      matchesIdentifier = true
      break
    }
  }

  let errorMessage: string | null = null
  if (!pw) {
    errorMessage = `Пароль не может быть пустым. Требования: не менее ${minLength} символов, буквы и цифры (разрешены спецсимволы).`
  } else if (matchesIdentifier) {
    errorMessage = `Пароль не должен совпадать с логином или email. Придумайте другой пароль: не менее ${minLength} символов, буквы и цифры (разрешены спецсимволы).`
  } else if (isCommon) {
    errorMessage = `Пароль слишком простой — легко угадывается. Придумайте более сложный пароль: не менее ${minLength} символов, включая буквы и цифры (разрешены спецсимволы).`
  } else if (!hasMinLength) {
    errorMessage = `Пароль слишком короткий (сейчас ${currentLength} симв.): нужно не менее ${minLength} символов. Требуются буквы и цифры (разрешены спецсимволы).`
  } else if (!hasLetter && !hasDigit) {
    errorMessage = `В пароле должны быть буквы и цифры. Требования: не менее ${minLength} символов, буквы и цифры (разрешены спецсимволы).`
  } else if (!hasLetter) {
    errorMessage = `В пароле отсутствуют буквы: добавьте хотя бы одну букву. Требования: не менее ${minLength} символов, буквы и цифры (разрешены спецсимволы).`
  } else if (!hasDigit) {
    errorMessage = `В пароле отсутствуют цифры: добавьте хотя бы одну цифру. Требования: не менее ${minLength} символов, буквы и цифры (разрешены спецсимволы).`
  }

  const isValid = !errorMessage

  return {
    currentLength,
    minLength,
    hasMinLength,
    hasLetter,
    hasDigit,
    isCommon,
    matchesIdentifier,
    isValid,
    errorMessage,
  }
}

export function validatePassword(
  password: string | null | undefined,
  identifiers: (string | null | undefined)[] = [],
): { valid: boolean; message: string | null } {
  const evaluation = evaluatePassword(password, identifiers)
  return {
    valid: evaluation.isValid,
    message: evaluation.errorMessage,
  }
}
