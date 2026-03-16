#!/usr/bin/env node
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

function copyFile(src, dest) {
  try {
    fs.mkdirSync(path.dirname(dest), { recursive: true })
    fs.copyFileSync(src, dest)
    console.log(`copied ${src} -> ${dest}`)
    return true
  } catch (e) {
    console.warn(`failed to copy ${src}: ${e.message}`)
    return false
  }
}

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const projectRoot = path.resolve(__dirname, '..')
const moduleBase = path.join(projectRoot, 'node_modules', '@fortawesome', 'fontawesome-free')
const srcMeta = path.join(moduleBase, 'metadata', 'icon-families.json')
const srcCss = path.join(moduleBase, 'css', 'all.css')
const srcWebfonts = path.join(moduleBase, 'webfonts')

const destBase = path.join(projectRoot, 'src', 'assets', 'fontawesome-free')
const destMeta = path.join(destBase, 'metadata', 'icon-families.json')
const destCss = path.join(destBase, 'css', 'all.css')
const destWebfonts = path.join(destBase, 'webfonts')

// also mirror into public so assets are available at /fontawesome-free/* without Vite processing
const destPublicBase = path.join(projectRoot, 'public', 'fontawesome-free')
const destPublicMeta = path.join(destPublicBase, 'metadata', 'icon-families.json')
const destPublicCss = path.join(destPublicBase, 'css', 'all.css')
const destPublicWebfonts = path.join(destPublicBase, 'webfonts')

function copyFolderSync (src, dest) {
  if (!fs.existsSync(src)) return false
  fs.mkdirSync(dest, { recursive: true })
  const entries = fs.readdirSync(src, { withFileTypes: true })
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name)
    const destPath = path.join(dest, entry.name)
    if (entry.isDirectory()) {
      copyFolderSync(srcPath, destPath)
    } else if (entry.isFile()) {
      try {
        fs.copyFileSync(srcPath, destPath)
        console.log(`copied ${srcPath} -> ${destPath}`)
      } catch (e) {
        console.warn(`failed to copy ${srcPath}: ${e.message}`)
      }
    }
  }
  return true
}

let copiedAnything = false

if (fs.existsSync(srcMeta)) {
  copyFile(srcMeta, destMeta)
  copyFile(srcMeta, destPublicMeta)
  copiedAnything = true
} else {
  console.warn('Font Awesome metadata not found in node_modules; skipping metadata copy.')
}

if (fs.existsSync(srcCss)) {
  copyFile(srcCss, destCss)
  copyFile(srcCss, destPublicCss)
  copiedAnything = true
} else {
  console.warn('Font Awesome CSS not found in node_modules; skipping css copy.')
}

if (fs.existsSync(srcWebfonts)) {
  copyFolderSync(srcWebfonts, destWebfonts)
  copyFolderSync(srcWebfonts, destPublicWebfonts)
  copiedAnything = true
} else {
  console.warn('Font Awesome webfonts not found in node_modules; skipping webfonts copy.')
}

// copy the css folder (includes v5-font-face.css and others) if present
const srcCssFolder = path.join(moduleBase, 'css')
const destCssFolder = path.join(destBase, 'css')
if (fs.existsSync(srcCssFolder)) {
  copyFolderSync(srcCssFolder, destCssFolder)
  copyFolderSync(srcCssFolder, path.join(destPublicBase, 'css'))
  copiedAnything = true
} else {
  console.warn('Font Awesome css folder not found; skipping css folder copy.')
}

if (!copiedAnything) {
  console.warn('No Font Awesome assets were copied. This is ok if the package is not installed.')
}

// exit code 0 regardless to avoid failing installs in environments where FA isn't present
process.exit(0)
