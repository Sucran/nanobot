/**
 * WhatsApp 客户端封装模块
 * 
 * 使用 Baileys 库实现 WhatsApp Web 客户端功能。
 * 基于 OpenClaw 的成熟实现。
 * 
 * 功能：
 * - WhatsApp Web 连接和认证
 * - 消息收发
 * - 二维码登录
 * - 自动重连
 * - 消息内容提取
 */

/* eslint-disable @typescript-eslint/no-explicit-any */
import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} from '@whiskeysockets/baileys';

import { Boom } from '@hapi/boom';
import qrcode from 'qrcode-terminal';
import pino from 'pino';

const VERSION = '0.1.0';

/**
 * 入站消息接口
 * 
 * 从 WhatsApp 接收到的消息结构
 */
export interface InboundMessage {
  id: string;           // 消息唯一 ID
  sender: string;       // 发送者 ID（手机号或群组 ID）
  content: string;      // 消息内容
  timestamp: number;    // 时间戳（Unix 时间）
  isGroup: boolean;     // 是否为群组消息
}

/**
 * WhatsApp 客户端选项接口
 */
export interface WhatsAppClientOptions {
  authDir: string;                                          // 认证数据存储目录
  onMessage: (msg: InboundMessage) => void;                 // 收到消息时的回调
  onQR: (qr: string) => void;                              // 显示二维码时的回调
  onStatus: (status: string) => void;                      // 状态变化时的回调
}

/**
 * WhatsApp 客户端类
 * 
 * 封装 Baileys 库，提供简洁的 WhatsApp 集成接口。
 */
export class WhatsAppClient {
  private sock: any = null;                    // Baileys socket 实例
  private options: WhatsAppClientOptions;      // 配置选项
  private reconnecting = false;                // 是否正在重连

  /**
   * 创建 WhatsApp 客户端实例
   * 
   * @param options - 客户端配置选项
   */
  constructor(options: WhatsAppClientOptions) {
    this.options = options;
  }

  /**
   * 连接 WhatsApp
   * 
   * 连接流程：
   * 1. 加载或创建认证状态
   * 2. 获取最新 Baileys 版本
   * 3. 创建 WebSocket 连接
   * 4. 设置事件监听器
   */
  async connect(): Promise<void> {
    // 创建静默 logger（减少输出噪音）
    const logger = pino({ level: 'silent' });
    
    // 加载认证状态（从文件）
    const { state, saveCreds } = await useMultiFileAuthState(this.options.authDir);
    
    // 获取最新版本
    const { version } = await fetchLatestBaileysVersion();
    console.log(`Using Baileys version: ${version.join('.')}`);

    // 创建 socket
    this.sock = makeWASocket({
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, logger),
      },
      version,
      logger,
      printQRInTerminal: false,           // 我们自己处理二维码显示
      browser: ['nanobot', 'cli', VERSION],
      syncFullHistory: false,             // 不同步历史消息
      markOnlineOnConnect: false,         // 连接时不显示在线状态
    });

    // 处理 WebSocket 错误
    if (this.sock.ws && typeof this.sock.ws.on === 'function') {
      this.sock.ws.on('error', (err: Error) => {
        console.error('WebSocket error:', err.message);
      });
    }

    // 处理连接状态更新
    this.sock.ev.on('connection.update', async (update: any) => {
      const { connection, lastDisconnect, qr } = update;

      // 显示二维码
      if (qr) {
        console.log('\n📱 请使用 WhatsApp 扫描二维码（已连接设备）：\n');
        qrcode.generate(qr, { small: true });
        this.options.onQR(qr);
      }

      // 连接关闭
      if (connection === 'close') {
        const statusCode = (lastDisconnect?.error as Boom)?.output?.statusCode;
        const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

        console.log(`Connection closed. Status: ${statusCode}, Will reconnect: ${shouldReconnect}`);
        this.options.onStatus('disconnected');

        // 自动重连（除非是主动登出）
        if (shouldReconnect && !this.reconnecting) {
          this.reconnecting = true;
          console.log('5秒后重新连接...');
          setTimeout(() => {
            this.reconnecting = false;
            this.connect();
          }, 5000);
        }
      } else if (connection === 'open') {
        // 连接成功
        console.log('✅ 已连接到 WhatsApp');
        this.options.onStatus('connected');
      }
    });

    // 保存认证信息更新
    this.sock.ev.on('creds.update', saveCreds);

    // 处理收到的消息
    this.sock.ev.on('messages.upsert', async ({ messages, type }: { messages: any[]; type: string }) => {
      if (type !== 'notify') return;  // 只处理通知类型的消息

      for (const msg of messages) {
        // 跳过自己发送的消息
        if (msg.key.fromMe) continue;

        // 跳过状态更新
        if (msg.key.remoteJid === 'status@broadcast') continue;

        // 提取消息内容
        const content = this.extractMessageContent(msg);
        if (!content) continue;

        const isGroup = msg.key.remoteJid?.endsWith('@g.us') || false;

        // 触发消息回调
        this.options.onMessage({
          id: msg.key.id || '',
          sender: msg.key.remoteJid || '',
          content,
          timestamp: msg.messageTimestamp as number,
          isGroup,
        });
      }
    });
  }

  /**
   * 提取消息内容
   * 
   * 支持的消息类型：
   * - 文本消息
   * - 回复消息（带引用）
   * - 图片（带说明）
   * - 视频（带说明）
   * - 文档（带说明）
   * - 语音消息
   * 
   * @param msg - Baileys 消息对象
   * @returns 提取的文本内容，如果不支持则返回 null
   */
  private extractMessageContent(msg: any): string | null {
    const message = msg.message;
    if (!message) return null;

    // 纯文本消息
    if (message.conversation) {
      return message.conversation;
    }

    // 扩展文本（回复、链接预览等）
    if (message.extendedTextMessage?.text) {
      return message.extendedTextMessage.text;
    }

    // 图片带说明
    if (message.imageMessage?.caption) {
      return `[Image] ${message.imageMessage.caption}`;
    }

    // 视频带说明
    if (message.videoMessage?.caption) {
      return `[Video] ${message.videoMessage.caption}`;
    }

    // 文档带说明
    if (message.documentMessage?.caption) {
      return `[Document] ${message.documentMessage.caption}`;
    }

    // 语音/音频消息
    if (message.audioMessage) {
      return `[Voice Message]`;
    }

    return null;
  }

  /**
   * 发送消息
   * 
   * @param to - 目标 ID（手机号或群组 ID）
   * @param text - 消息内容
   */
  async sendMessage(to: string, text: string): Promise<void> {
    if (!this.sock) {
      throw new Error('Not connected');
    }

    await this.sock.sendMessage(to, { text });
  }

  /**
   * 断开连接
   * 
   * 关闭 WebSocket 连接并清理资源
   */
  async disconnect(): Promise<void> {
    if (this.sock) {
      this.sock.end(undefined);
      this.sock = null;
    }
  }
}
