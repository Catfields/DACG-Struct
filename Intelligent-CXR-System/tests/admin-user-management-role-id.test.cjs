const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const componentPath = path.resolve(
  __dirname,
  '../src/components/AdminUserManagement.vue'
)
const source = fs.readFileSync(componentPath, 'utf8')

function readConstNumber(name) {
  const match = source.match(new RegExp(`const\\s+${name}\\s*=\\s*(\\d+)`))
  assert.ok(match, `未找到常量 ${name}`)
  return Number(match[1])
}

test('主治医生默认 role_id 应为 2', () => {
  const attendingRoleId = readConstNumber('DEFAULT_ROLE_ID_ATTENDING')
  assert.equal(attendingRoleId, 2)
})

test('影像科医生默认 role_id 应为 1', () => {
  const radiologistRoleId = readConstNumber('DEFAULT_ROLE_ID_RADIOLOGIST')
  assert.equal(radiologistRoleId, 1)
})
