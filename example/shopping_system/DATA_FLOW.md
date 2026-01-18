# 数据流设计文档
# 跨平台电商中台系统 - 数据架构与流转设计

---

## 文档信息
- **版本号**: v1.0
- **创建日期**: 2026-01-18
- **技术栈**: Python + MySQL + Redis + RabbitMQ

---

## 1. 核心数据实体设计

### 1.1 数据实体关系图 (ERD)

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│   Platform  │         │   Merchant  │         │  Product    │
│  (平台表)    │         │  (商户表)    │         │  (商品表)    │
├─────────────┤         ├─────────────┤         ├─────────────┤
│ id          │────┐    │ id          │────┐    │ id          │
│ name        │    │    │ name        │    │    │ merchant_id │─┐
│ type        │    │    │ platform_id │─┘    │ name        │ │
│ config      │    │    │ status      │         │ category_id │ │
│ status      │    │    └─────────────┘         │ brand_id    │ │
└─────────────┘    │                            │ status      │ │
                   │                            └──────┬──────┘
┌─────────────┐    │                                   │
│  Customer   │    │         ┌─────────────┐           │
│  (用户表)    │    │         │     SKU     │           │
├─────────────┤    │         │  (SKU表)     │           │
│ id          │    │         ├─────────────┤           │
│ phone       │    │         │ id          │           │
│ nickname    │    │         │ product_id  │───────────┘
│ avatar      │    │         │ specs       │
│ platform_id │─┘    │         │ price       │
│ union_id    │─────┘         │ cost        │
│ level       │              │ stock       │
└─────────────┘              └──────┬──────┘
                                    │
      ┌─────────────┐               │
      │   Order     │               │
      │  (订单表)    │               │
      ├─────────────┤               │
      │ id          │               │
      │ order_no    │               │
      │ merchant_id │───────────────┘
      │ customer_id │
      │ platform_id │
      │ total_amount│
      │ status      │
      └──────┬──────┘
             │
      ┌──────┴──────┐
      │             │
┌─────┴─────┐  ┌────┴─────┐
│ OrderItem  │  │ Shipment │
│ (订单明细)  │  │ (发货单)  │
├───────────┤  ├──────────┤
│ id         │  │ id       │
│ order_id   │  │ order_id │
│ sku_id     │  │ carrier  │
│ quantity   │  │ tracking_no
│ price      │  │ status   │
└───────────┘  └──────────┘
```

### 1.2 核心数据表结构

#### 1.2.1 商品中心 (Product & SKU)

**商品表 (products)**:
```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    merchant_id BIGINT NOT NULL,              -- 商户ID
    name VARCHAR(200) NOT NULL,               -- 商品名称
    category_id INT NOT NULL,                 -- 类目ID
    brand_id INT,                             -- 品牌ID
    type ENUM('physical', 'virtual', 'course', 'membership') NOT NULL,  -- 商品类型
    status ENUM('draft', 'online', 'offline') DEFAULT 'draft',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_merchant_id (merchant_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**SKU表 (skus)**:
```sql
CREATE TABLE skus (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    product_id BIGINT NOT NULL,               -- 商品ID
    sku_code VARCHAR(50) NOT NULL UNIQUE,     -- SKU编码
    specs JSON,                               -- 规格属性 {"颜色": "红色", "尺码": "XL"}
    cost_price DECIMAL(10,2),                 -- 成本价
    original_price DECIMAL(10,2),             -- 原价
    stock INT DEFAULT 0,                      -- 物理库存
    available_stock INT DEFAULT 0,            -- 可用库存
    locked_stock INT DEFAULT 0,               -- 锁定库存
    weight INT,                               -- 重量(克)
    status ENUM('online', 'offline') DEFAULT 'online',
    INDEX idx_product_id (product_id),
    INDEX idx_sku_code (sku_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**多渠道价格表 (sku_channel_prices)**:
```sql
CREATE TABLE sku_channel_prices (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    sku_id BIGINT NOT NULL,                   -- SKU ID
    channel ENUM('wechat', 'alipay', 'taobao', 'xiaohongshu', 'douyin') NOT NULL,
    price DECIMAL(10,2) NOT NULL,             -- 渠道售价
    vip_price DECIMAL(10,2),                  -- 会员价
    effective_date DATE,                      -- 生效日期
    expire_date DATE,                         -- 失效日期
    UNIQUE KEY uk_sku_channel (sku_id, channel),
    INDEX idx_channel (channel)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 1.2.2 订单中心 (Order)

**订单表 (orders)**:
```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    order_no VARCHAR(32) NOT NULL UNIQUE,     -- 订单号
    merchant_id BIGINT NOT NULL,              -- 商户ID
    customer_id BIGINT NOT NULL,              -- 用户ID
    platform ENUM('wechat', 'alipay', 'taobao', 'xiaohongshu', 'douyin') NOT NULL,
    platform_order_id VARCHAR(64),            -- 第三方平台订单ID

    -- 金额信息
    total_amount DECIMAL(10,2) NOT NULL,      -- 订单总金额
    discount_amount DECIMAL(10,2) DEFAULT 0,  -- 优惠金额
    freight_amount DECIMAL(10,2) DEFAULT 0,   -- 运费
    pay_amount DECIMAL(10,2) NOT NULL,        -- 实付金额

    -- 收货信息
    receiver_name VARCHAR(50),
    receiver_phone VARCHAR(20),
    receiver_address VARCHAR(500),
    receiver_province VARCHAR(50),
    receiver_city VARCHAR(50),
    receiver_district VARCHAR(50),

    -- 订单状态
    status ENUM('unpaid', 'pending', 'shipped', 'completed', 'cancelled', 'refunding') DEFAULT 'unpaid',
    pay_time DATETIME,                        -- 支付时间
    ship_time DATETIME,                       -- 发货时间
    complete_time DATETIME,                   -- 完成时间

    -- 其他
    remark VARCHAR(500),                      -- 订单备注
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_merchant_id (merchant_id),
    INDEX idx_customer_id (customer_id),
    INDEX idx_platform (platform),
    INDEX idx_platform_order_id (platform_order_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**订单明细表 (order_items)**:
```sql
CREATE TABLE order_items (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    order_id BIGINT NOT NULL,                 -- 订单ID
    sku_id BIGINT NOT NULL,                   -- SKU ID
    sku_name VARCHAR(200),                    -- SKU名称
    sku_specs JSON,                           -- SKU规格
    quantity INT NOT NULL,                    -- 数量
    price DECIMAL(10,2) NOT NULL,             -- 单价
    total_amount DECIMAL(10,2) NOT NULL,      -- 小计金额
    INDEX idx_order_id (order_id),
    INDEX idx_sku_id (sku_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 1.2.3 用户中心 (Customer)

**用户表 (customers)**:
```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    merchant_id BIGINT NOT NULL,              -- 商户ID
    phone VARCHAR(20) NOT NULL,               -- 手机号 (跨平台身份识别)
    nickname VARCHAR(100),                    -- 昵称
    avatar VARCHAR(500),                      -- 头像
    gender ENUM('male', 'female', 'unknown') DEFAULT 'unknown',
    birthday DATE,                            -- 生日
    province VARCHAR(50),                     -- 省份
    city VARCHAR(50),                         -- 城市

    -- 会员信息
    level ENUM('normal', 'monthly', 'yearly') DEFAULT 'normal',
    level_expire_time DATETIME,               -- 会员到期时间
    points INT DEFAULT 0,                     -- 积分

    -- 跨平台身份
    wechat_openid VARCHAR(64),                -- 微信OpenID
    wechat_unionid VARCHAR(64),               -- 微信UnionID
    alipay_user_id VARCHAR(64),               -- 支付宝用户ID
    taobao_nick VARCHAR(100),                 -- 淘宝昵称

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_merchant_phone (merchant_id, phone),
    INDEX idx_wechat_unionid (wechat_unionid),
    INDEX idx_level (level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 1.2.4 发货与物流 (Shipment)

**发货单表 (shipments)**:
```sql
CREATE TABLE shipments (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    shipment_no VARCHAR(32) NOT NULL UNIQUE,  -- 发货单号
    order_id BIGINT NOT NULL,                 -- 订单ID
    order_item_ids JSON,                      -- 订单明细IDs (支持拆单)
    carrier ENUM('sf', 'sto', 'yt', 'ems', 'yunda', 'post') NOT NULL,  -- 快递公司
    tracking_no VARCHAR(50) NOT NULL,         -- 物流单号
    ship_time DATETIME NOT NULL,              -- 发货时间
    status ENUM('shipping', 'delivered', 'returned') DEFAULT 'shipping',
    delivered_time DATETIME,                  -- 签收时间
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_order_id (order_id),
    INDEX idx_tracking_no (tracking_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 1.2.5 会员与积分 (Member & Points)

**积分流水表 (point_transactions)**:
```sql
CREATE TABLE point_transactions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    customer_id BIGINT NOT NULL,              -- 用户ID
    amount INT NOT NULL,                      -- 积分变动 (正数=增加, 负数=扣减)
    type ENUM('consume', 'refund', 'sign', 'task', 'manual') NOT NULL,  -- 类型
    source VARCHAR(50),                       -- 来源 (订单ID, 任务ID等)
    remark VARCHAR(200),                      -- 备注
    balance INT NOT NULL,                     -- 变动后余额
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_customer_id (customer_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 1.2.6 财务与分账 (Finance)

**分账单表 (settlement_orders)**:
```sql
CREATE TABLE settlement_orders (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    settlement_no VARCHAR(32) NOT NULL UNIQUE,  -- 分账单号
    order_id BIGINT NOT NULL,                  -- 订单ID
    total_amount DECIMAL(10,2) NOT NULL,       -- 订单总金额
    settlement_amount DECIMAL(10,2) NOT NULL,  -- 分账金额

    -- 分账规则
    settlement_rules JSON,                     -- 分账规则

    -- 分账明细
    settlement_details JSON,                   -- 分账明细

    status ENUM('pending', 'completed', 'failed') DEFAULT 'pending',
    settled_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_order_id (order_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 2. 核心业务流程数据流

### 2.1 订单创建流程

#### 2.1.1 自营渠道下单 (微信/支付宝小程序)

```
用户下单
    ↓
【前端】调用 POST /api/v1/orders/create
    {
        "sku_items": [
            {"sku_id": 123, "quantity": 2}
        ],
        "receiver_info": {...}
    }
    ↓
【后端】OrderService.create_order()
    ↓
    1. 校验SKU状态 + 库存
    2. 计算订单金额 (查询 sku_channel_prices)
    3. 生成订单号 (merchant_id + timestamp + random)
    4. 创建订单记录 (orders + order_items)
    5. 锁定库存 (skus.locked_stock += quantity)
    ↓
    写入 MySQL (事务)
    ↓
    返回订单号
```

#### 2.1.2 第三方平台订单同步 (淘宝/抖音)

```
【定时任务】每5分钟执行一次
    ↓
【平台API适配器】TaobaoOrderSyncService.fetch_orders()
    ↓
    1. 调用淘宝 TOP API: taobao.trades.sold.get
    2. 获取最近5分钟增量订单
    ↓
【数据处理】OrderSyncService.process_raw_order()
    ↓
    1. 解析淘宝订单数据
    2. 通过手机号查询/创建本地用户
       - SELECT * FROM customers WHERE phone = ?
       - 若不存在, 则创建新用户
    3. 映射商品:
       - 通过 SKU外部编码 查询本地SKU
       - SELECT * FROM skus WHERE sku_code = ?
    4. 创建本地订单:
       - INSERT INTO orders (..., platform_order_id = '淘宝订单号')
       - INSERT INTO order_items
    5. 同步库存状态:
       - 若淘宝已扣库存, 则本地也要扣减
    ↓
    写入 MySQL
    ↓
    标记同步状态: 防止重复同步
```

---

### 2.2 库存扣减流程 (分布式锁)

#### 2.2.1 下单锁定库存

```
用户下单
    ↓
【库存服务】InventoryService.lock_stock()
    ↓
    1. 获取分布式锁
       - Redis key: "inventory:lock:sku_id:123"
       - SET NX EX 15 (15秒超时)
    ↓
    2. 查询库存
       - SELECT stock, available_stock FROM skus WHERE id = 123 FOR UPDATE
    ↓
    3. 校验库存
       - IF available_stock >= quantity THEN
            - UPDATE skus SET available_stock -= 2, locked_stock += 2
         ELSE
            - 抛出库存不足异常
    ↓
    4. 释放锁
       - DEL "inventory:lock:sku_id:123"
    ↓
    5. 发送库存锁定消息 (RabbitMQ)
       - 用于订单超时自动释放
```

#### 2.2.2 支付成功扣减库存

```
支付回调 (微信/支付宝)
    ↓
【支付服务】PaymentService.handle_callback()
    ↓
    1. 校验签名
    2. 查询订单: SELECT * FROM orders WHERE order_no = ?
    3. 更新订单状态: UPDATE orders SET status = 'pending', pay_time = NOW()
    ↓
    4. 扣减库存
       - UPDATE skus SET stock -= 2, locked_stock -= 2 WHERE id = 123
    ↓
    5. 发送支付成功消息 (RabbitMQ)
       - 触发后续流程 (发货通知、积分奖励)
```

#### 2.2.3 订单超时释放库存

```
【定时任务】每分钟扫描超时订单
    ↓
    1. 查询超时未支付订单
       - SELECT * FROM orders WHERE status = 'unpaid' AND created_at < NOW() - 15min
    ↓
    2. 批量取消订单
       - UPDATE orders SET status = 'cancelled'
    ↓
    3. 释放库存
       - UPDATE skus SET locked_stock -= 2, available_stock += 2 WHERE id = 123
    ↓
    4. 发送取消通知 (用户微信/短信)
```

---

### 2.3 发货与物流同步流程

#### 2.3.1 打印发货单

```
【运营后台】点击"打印面单"
    ↓
【发货服务】ShipmentService.print_waybill()
    ↓
    1. 查询订单信息 (收货地址、商品重量)
    ↓
    2. 智能路由: 选择最优快递公司
       - IF 地址在江浙沪 THEN 中通
         ELSE IF 地址在偏远 THEN 邮政EMS
         ELSE 顺丰
    ↓
    3. 调用快递鸟API获取电子面单
       - POST https://api.kdniao.com/api/EorderService
       - 参数: 订单号、收货信息、快递公司
    ↓
    4. 返回电子面单PDF
    ↓
    5. 创建发货单记录
       - INSERT INTO shipments (shipment_no, order_id, carrier, tracking_no)
    ↓
    6. 返回PDF (前端下载打印)
```

#### 2.3.2 发货并回填第三方平台

```
【运营后台】点击"确认发货"
    ↓
【发货服务】ShipmentService.confirm_ship()
    ↓
    1. 更新本地订单状态
       - UPDATE orders SET status = 'shipped', ship_time = NOW()
    ↓
    2. 回填第三方平台 (根据订单来源)
       - IF 平台 = 淘宝 THEN
            - 调用淘宝 API: taobao.logistics.online.send
            - 参数: tid=淘宝订单号, company_code=快递公司, logistics_no=单号
         ELSE IF 平台 = 抖音 THEN
            - 调用抖音 API: logistics.order.online.confirm
    ↓
    3. 发送发货通知 (微信订阅消息 / 短信)
       - "您的订单已发货,顺丰单号: SF1234567890"
```

#### 2.3.3 物流轨迹同步

```
【定时任务】每2小时执行
    ↓
【物流服务】LogisticsService.sync_tracking()
    ↓
    1. 查询在途发货单
       - SELECT * FROM shipments WHERE status = 'shipping'
    ↓
    2. 批量调用快递100 API
       - POST https://api.kuaidi100.com/pollquery
       - 参数: [tracking_no_list]
    ↓
    3. 解析物流轨迹
       - IF 最新状态 = "已签收" THEN
            - UPDATE shipments SET status = 'delivered', delivered_time = ?
            - UPDATE orders SET status = 'completed'
    ↓
    4. 缓存物流轨迹 (Redis, TTL=1小时)
       - HSET logistics:tracking:SF1234567890 "轨迹JSON"
```

---

### 2.4 会员身份融合流程

#### 2.4.1 新用户注册/下单

```
用户首次下单 (淘宝)
    ↓
【用户服务】CustomerService.get_or_create_customer()
    ↓
    1. 接收淘宝订单数据 (手机号: 13800138000)
    ↓
    2. 查询本地用户
       - SELECT * FROM customers WHERE phone = '13800138000'
    ↓
    3. IF 用户不存在 THEN
        - 创建用户:
            INSERT INTO customers (
                phone, taobao_nick='淘宝昵称', level='normal'
            )
        - 返回新用户ID
       ELSE IF 用户已存在 THEN
        - 更新淘宝昵称 (为空时)
            UPDATE customers SET taobao_nick='淘宝昵称' WHERE id = ?
        - 返回已有用户ID
    ↓
    4. 关联订单
       - UPDATE orders SET customer_id = ? WHERE order_no = ?
```

#### 2.4.2 跨平台身份识别

```
场景: 用户先在淘宝下单, 后在微信小程序下单
    ↓
【微信小程序】用户授权登录 (获取微信手机号)
    ↓
【用户服务】CustomerService.wechat_login()
    ↓
    1. 获取微信手机号: 13800138000
    ↓
    2. 查询本地用户
       - SELECT * FROM customers WHERE phone = '13800138000'
    ↓
    3. 发现用户已存在 (之前在淘宝下过单)
    ↓
    4. 更新微信信息
       - UPDATE customers SET
            wechat_openid='微信OpenID',
            wechat_unionid='微信UnionID'
         WHERE id = ?
    ↓
    5. 返回用户信息 (前端展示: "欢迎回来, 淘宝昵称")
    ↓
    6. 用户可以看到:
        - 淘宝订单历史
        - 微信积分
        - 跨平台累计消费金额
```

---

### 2.5 积分获取与消费流程

#### 2.5.1 消费获得积分

```
订单完成
    ↓
【积分服务】PointService.grant_points()
    ↓
    1. 查询订单
       - SELECT * FROM orders WHERE id = ?
    ↓
    2. 计算积分: 订单金额 * 积分比例 (1元 = 1积分)
       - points = order.pay_amount
    ↓
    3. 会员加成
       - IF user.level = 'yearly' THEN points *= 1.5
    ↓
    4. 增加积分
       - UPDATE customers SET points += ? WHERE id = ?
    ↓
    5. 记录流水
       - INSERT INTO point_transactions (
            customer_id, amount=100, type='consume',
            source='order:123', balance=1500
         )
    ↓
    6. 发送积分到账通知 (微信/短信)
```

#### 2.5.2 积分兑换商品

```
用户使用积分兑换周边商品
    ↓
【积分服务】PointService.redeem_goods()
    ↓
    1. 校验积分余额
       - SELECT points FROM customers WHERE id = ?
    ↓
    2. 扣减积分
       - UPDATE customers SET points -= 1000 WHERE id = ?
    ↓
    3. 记录流水
       - INSERT INTO point_transactions (
            customer_id, amount=-1000, type='redeem',
            source='redeem:goods:456', balance=500
         )
    ↓
    4. 创建兑换订单
       - INSERT INTO orders (..., total_amount=0, pay_amount=0, status='completed')
       - INSERT INTO order_items (sku_id=兑换商品ID, quantity=1, price=0)
    ↓
    5. 触发发货流程
```

---

### 2.6 客服工作台数据流

#### 2.6.1 全渠道消息聚合

```
【消息同步服务】MessageSyncService.pull_messages()
    ↓
    ↓────────────────────┬────────────────────┐
    ↓                    ↓                    ↓
【微信小程序】       【淘宝旺旺】         【抖音客服】
    ↓                    ↓                    ↓
    ↓                    ↓                    ↓
┌────────────────────────────────────────────────┐
│           统一消息表 (messages)                  │
├────────────────────────────────────────────────┤
│ id                                             │
│ customer_id    ← 关联本地用户                  │
│ platform       ← 来源平台                      │
│ platform_msg_id ← 第三方消息ID                 │
│ direction      ← incoming/outgoing            │
│ content        ← 消息内容                      │
│ msg_type       ← text/image/order             │
│ read_status    ← 是否已读                     │
│ created_at                                    │
└────────────────────────────────────────────────┘
    ↓
【前端】聚合展示:
    - 按 customer_id 分组
    - 按 created_at 排序
    - 显示最新一条消息预览
```

#### 2.6.2 AI自动回复流程

```
用户发送消息: "我的订单发货了吗?"
    ↓
【AI客服服务】AICSService.handle_message()
    ↓
    1. 意图识别 (调用大模型)
       - Prompt: "用户消息: {content}, 识别意图"
       - 返回: "query_order_status"
    ↓
    2. 提取参数
       - 识别手机号 (从消息中提取 或 根据customer_id查询)
       - SELECT phone FROM customers WHERE id = ?
    ↓
    3. 执行业务逻辑
       - IF 意图 = "query_order_status" THEN
            - 查询最新订单: SELECT * FROM orders WHERE customer_id = ? ORDER BY created_at DESC LIMIT 1
            - 查询物流: SELECT * FROM shipments WHERE order_id = ?
            - 生成回复: "您的订单已发货,顺丰单号: SF1234567890, 预计明天送达"
    ↓
    4. 判断是否需要人工介入
       - IF 意图识别置信度 < 0.7 THEN
            - 转人工客服
       - ELSE
            - 自动发送回复
    ↓
    5. 记录对话日志
       - INSERT INTO ai_conversation_logs (...)
```

---

### 2.7 财务对账流程

#### 2.7.1 每日自动对账

```
【定时任务】每日凌晨2点执行
    ↓
【对账服务】ReconciliationService.daily_reconcile()
    ↓
    1. 拉取平台账单
       - 支付宝: 调用 alipay.data.bill.balance.query
       - 微信: 调用下载账单API
       - 淘宝: 调用 taobao.bill.accounts.get
    ↓
    2. 解析账单数据
       - 解析CSV/Excel
       - 提取关键字段: 订单号、金额、手续费
    ↓
    3. 与本地订单比对
       - SELECT * FROM orders WHERE DATE(pay_time) = '2026-01-17'
       - 比对:
            - 订单数是否一致
            - 订单金额是否一致
    ↓
    4. 生成对账报告
       - 一致订单数: 100
       - 差异订单数: 2
       - 差异金额: +10.5元
    ↓
    5. 差异订单标记
       - INSERT INTO reconciliation_exceptions (...)
       - 发送告警通知 (邮件/钉钉)
```

#### 2.7.2 自动分账流程

```
订单完成 (status = 'completed')
    ↓
【分账服务】SettlementService.create_settlement()
    ↓
    1. 查询商品分账规则
       - SELECT settlement_rules FROM products WHERE id = ?
       - 例: {"partners": [{"name": "设计师A", "type": "percent", "value": 30}]}
    ↓
    2. 计算分账金额
       - 订单毛利 = 订单金额 - 成本价 - 运费
       - 设计师A分账 = 订单毛利 * 30% = 100元
    ↓
    3. 生成分账单
       - INSERT INTO settlement_orders (
            settlement_no, order_id, total_amount, settlement_amount,
            settlement_rules, settlement_details
         )
    ↓
    4. 财务审核
       - 财务人员登录后台
       - 查看分账单列表
       - 确认无误后点击"确认打款"
    ↓
    5. 自动打款
       - 调用支付宝/微信转账API
       - 转账到设计师账户
    ↓
    6. 更新分账状态
       - UPDATE settlement_orders SET status = 'completed', settled_at = NOW()
```

---

## 3. 数据流转架构图

### 3.1 系统间数据流转

```
┌──────────────────────────────────────────────────────────────┐
│                         外部系统                              │
├──────────────────────────────────────────────────────────────┤
│  淘宝TOP API  │  抖音抖店API  │  快递鸟API  │  微信支付API     │
└────────┬───────────────┬───────────────┬─────────────────────┘
         ↓               ↓               ↓
         │               │               │
┌────────┴───────────────┴───────────────┴─────────────────────┐
│                    API Gateway (Kong)                         │
│           (统一鉴权、限流、日志记录)                           │
└────────┬───────────────┬───────────────┬─────────────────────┘
         ↓               ↓               ↓
┌────────┴───────────────┴───────────────┴─────────────────────┐
│                   业务中台微服务群                            │
├──────────────────────────────────────────────────────────────┤
│  商品服务  │  订单服务  │  库存服务  │  用户服务  │  支付服务  │
└────────┬───────────────┬───────────────┬─────────────────────┘
         ↓               ↓               ↓
┌────────┴───────────────┴───────────────┴─────────────────────┐
│                   消息队列 (RabbitMQ)                         │
│  (订单创建、支付成功、发货通知、积分变动)                      │
└────────┬───────────────┬───────────────┬─────────────────────┘
         ↓               ↓               ↓
┌────────┴───────────────┴───────────────┴─────────────────────┐
│                   数据存储层                                  │
├──────────────────────────────────────────────────────────────┤
│  MySQL集群  │  Redis集群  │  Elasticsearch  │  对象存储(OSS)  │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 订单全生命周期数据流

```
【渠道层】
    ↓
用户下单 (微信小程序/淘宝/抖音)
    ↓
【API网关】
    ↓ 路由到订单服务
【订单服务】OrderService.create_order()
    ↓ 发送"订单创建"消息
【消息队列】RabbitMQ
    ↓ 消费消息
    ├─→【库存服务】锁定库存
    ├─→【用户服务】记录用户行为
    └─→【营销服务】发送优惠券推荐
    ↓
用户支付
    ↓ 支付回调
【支付服务】PaymentService.handle_callback()
    ↓ 发送"支付成功"消息
【消息队列】RabbitMQ
    ↓ 消费消息
    ├─→【订单服务】更新订单状态
    ├─→【库存服务】扣减库存
    ├─→【积分服务】增加积分
    └─→【通知服务】发送支付成功通知
    ↓
运营人员发货
    ↓ 调用快递鸟API
【发货服务】ShipmentService.print_waybill()
    ↓ 发送"已发货"消息
【消息队列】RabbitMQ
    ↓ 消费消息
    ├─→【订单服务】更新订单状态
    ├─→【第三方平台同步服务】回填淘宝/抖音
    └─→【通知服务】发送发货通知 (微信订阅消息)
    ↓
用户签收
    ↓ 定时任务同步物流
【物流服务】LogisticsService.sync_tracking()
    ↓ 发送"订单完成"消息
【消息队列】RabbitMQ
    ↓ 消费消息
    ├─→【订单服务】更新订单状态
    ├─→【分账服务】生成分账单
    └─→【会员服务】检查会员升级
```

---

## 4. 数据同步策略

### 4.1 实时同步 (使用消息队列)

**适用场景**:
- 订单状态变更
- 支付成功
- 库存变动
- 用户行为埋点

**技术方案**:
```python
# 生产者: 订单服务
def create_order(order_data):
    order = Order.create(order_data)

    # 发送消息到RabbitMQ
    rabbitmq.publish(
        exchange="order_events",
        routing_key="order.created",
        message={
            "order_id": order.id,
            "customer_id": order.customer_id,
            "amount": order.total_amount
        }
    )

# 消费者: 库存服务
@rabbitmq.consumer(queue="order_created_queue")
def handle_order_created(message):
    lock_stock(message["order_id"])
```

### 4.2 准实时同步 (定时任务)

**适用场景**:
- 第三方平台订单同步 (每5分钟)
- 物流轨迹同步 (每2小时)
- 财务对账 (每日凌晨)

**技术方案**:
```python
# Celery Beat 定时任务
@app.task
def sync_taobao_orders():
    # 拉取最近5分钟的订单
    orders = taobao_api.fetch_orders(minutes=5)

    for order in orders:
        process_order(order)

# 配置: 每5分钟执行一次
beat_schedule = {
    'sync-taobao-orders': {
        'task': 'tasks.sync_taobao_orders',
        'schedule': crontab(minute='*/5'),
    },
}
```

### 4.3 数据一致性保证

**最终一致性方案**:
1. **本地消息表**:
   - 订单服务写库时, 同时写消息表
   - 定时任务扫描消息表, 发送未发送的消息

2. **幂等性设计**:
   - 消息体包含唯一ID: `message_id`
   - 消费者处理前先检查是否已处理:
     ```python
     if redis.exists(f"processed:{message_id}"):
         return  # 已处理,跳过
     ```

3. **失败重试**:
   - RabbitMQ死信队列
   - 最多重试3次
   - 仍失败则记录到异常表, 人工介入

---

## 5. 核心数据结构示例

### 5.1 订单完整数据结构

```json
{
  "order": {
    "id": 123456,
    "order_no": "ORD2026011800001",
    "merchant_id": 100,
    "customer": {
      "id": 5001,
      "phone": "13800138000",
      "nickname": "小红书用户A",
      "level": "yearly"
    },
    "platform": "xiaohongshu",
    "platform_order_id": "XHS20260118001",
    "items": [
      {
        "sku_id": 2001,
        "sku_name": "Up主联名T恤-红色-XL",
        "specs": {"颜色": "红色", "尺码": "XL"},
        "quantity": 2,
        "price": 99.00,
        "total_amount": 198.00
      }
    ],
    "amount": {
      "total_amount": 198.00,
      "discount_amount": 19.80,
      "freight_amount": 10.00,
      "pay_amount": 188.20
    },
    "receiver": {
      "name": "张三",
      "phone": "138****8000",
      "province": "浙江省",
      "city": "杭州市",
      "district": "余杭区",
      "address": "文一西路969号"
    },
    "status": "shipped",
    "pay_time": "2026-01-18 10:30:00",
    "ship_time": "2026-01-18 16:00:00",
    "shipment": {
      "carrier": "sf",
      "carrier_name": "顺丰速运",
      "tracking_no": "SF1234567890"
    }
  }
}
```

### 5.2 商品完整数据结构

```json
{
  "product": {
    "id": 1001,
    "merchant_id": 100,
    "name": "Up主联名T恤",
    "category": "服装/ Tee",
    "brand": "Up主品牌",
    "type": "physical",
    "status": "online",
    "skus": [
      {
        "id": 2001,
        "sku_code": "SKU-TSHIRT-RED-XL",
        "specs": {"颜色": "红色", "尺码": "XL"},
        "cost_price": 50.00,
        "original_price": 129.00,
        "channel_prices": {
          "wechat": 99.00,
          "taobao": 109.00,
          "xiaohongshu": 99.00
        },
        "stock": 1000,
        "available_stock": 850,
        "locked_stock": 150
      }
    ],
    "images": {
      "main": "https://cdn.example.com/product/1001/main.jpg",
      "detail": [
        "https://cdn.example.com/product/1001/detail_1.jpg",
        "https://cdn.example.com/product/1001/detail_2.jpg"
      ]
    },
    "videos": {
      "short": "https://cdn.example.com/product/1001/short_15s.mp4"
    }
  }
}
```

### 5.3 用户完整数据结构

```json
{
  "customer": {
    "id": 5001,
    "phone": "13800138000",
    "nickname": "小红书用户A",
    "avatar": "https://cdn.example.com/avatar/5001.jpg",
    "gender": "female",
    "level": "yearly",
    "level_expire_time": "2026-12-31 23:59:59",
    "points": 2500,
    "platform_identity": {
      "wechat": {
        "openid": "oXXXX-xxxxxxxxxxxxxxxx",
        "unionid": "uxXXXX-xxxxxxxxxxxxxxxx"
      },
      "taobao": {
        "nick": "淘宝用户A"
      },
      "xiaohongshu": {
        "user_id": "XHS123456"
      }
    },
    "statistics": {
      "total_orders": 15,
      "total_amount": 2500.00,
      "avg_amount": 166.67,
      "last_order_time": "2026-01-18 10:30:00"
    }
  }
}
```

---

## 6. 数据监控与告警

### 6.1 关键指标监控

**订单监控**:
- 每分钟订单量
- 订单创建成功率
- 订单支付转化率

**库存监控**:
- 实时库存水位
- 库存预警 (低于阈值自动告警)
- 超卖监控 (库存 < 0 立即告警)

**第三方平台同步监控**:
- API调用成功率
- API响应时间
- 漏单检测 (本地订单数 vs 平台订单数)

### 6.2 告警规则

| 监控项 | 阈值 | 告警方式 |
|-------|------|---------|
| API调用失败率 | > 5% | 钉钉群 |
| 库存超卖 | 发生1次 | 钉钉群 + 短信 |
| 订单同步延迟 | > 10分钟 | 钉钉群 |
| 对账差异 | 任何差异 | 邮件 + 钉钉群 |

---

## 7. 数据备份与恢复

### 7.1 备份策略

**MySQL备份**:
- 全量备份: 每日凌晨3点 (使用 mysqldump)
- 增量备份: 每小时一次 (binlog)
- 保留期限: 30天

**Redis备份**:
- RDB快照: 每6小时
- AOF日志: 实时追加
- 保留期限: 7天

### 7.2 灾难恢复

**RTO (Recovery Time Objective)**: 4小时
**RPO (Recovery Point Objective)**: 1小时

**恢复流程**:
1. 恢复最新全量备份
2. 应用增量备份
3. 验证数据一致性
4. 切换流量

---

**文档结束**
