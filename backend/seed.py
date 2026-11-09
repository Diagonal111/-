from datetime import timedelta
from .store import dump, now, today

KNOWLEDGE = [
    ('cache', '计算机组成原理', '存储系统', 'Cache 地址映射'),
    ('memory', '计算机组成原理', '存储系统', '存储器容量计算'),
    ('pipeline', '计算机组成原理', '中央处理器', '指令流水线'),
    ('page', '操作系统', '内存管理', '分页与地址转换'),
    ('schedule', '操作系统', '进程管理', '进程调度'),
    ('deadlock', '操作系统', '进程管理', '死锁与安全状态'),
    ('tcp', '计算机网络', '传输层', 'TCP 可靠传输'),
    ('subnet', '计算机网络', '网络层', '子网划分'),
    ('http', '计算机网络', '应用层', 'HTTP 与 DNS'),
    ('tree', '数据结构', '树与二叉树', '二叉树与遍历'),
    ('sort', '数据结构', '排序', '排序算法'),
    ('graph', '数据结构', '图', '最短路径'),
]

# Original, deliberately small example questions. These are not official exam questions.
QUESTIONS = [
    ('q_cache', 'cache', 'calculation', 'Cache 地址如何拆分？', '某计算机按字节编址，主存地址为 **32 位**。Cache 采用直接映射，总数据容量为 **16 KB**，每个块为 **64 B**。\n\n求主存地址中的：\n1. 块内地址位数；\n2. Cache 行号位数；\n3. 标记（Tag）位数。', [], '块内地址 6 位；行号 8 位；标记 18 位。', '块大小为 $64=2^6$ B，故块内地址为 6 位。Cache 行数为 $16\\times1024/64=256=2^8$，行号为 8 位。标记为 $32-8-6=18$ 位。', 12),
    ('q_page', 'page', 'calculation', '从虚拟地址到物理地址', '某系统采用分页存储管理，页面大小为 **4 KB**。虚拟地址为十六进制 **0x3A7F**，其所在虚页映射到物理页框号 **5**。\n\n求虚页号、页内偏移和对应的物理地址。', [], '虚页号 3；页内偏移 0xA7F；物理地址 0x5A7F。', '4 KB 页面对应 12 位页内偏移。虚页号为 3，偏移为 0xA7F。物理页框号 5 与页内偏移拼接，得到 0x5A7F。', 12),
    ('q_schedule', 'schedule', 'single', '时间片轮转调度的特点', '下列关于时间片轮转（RR）调度的叙述，正确的是？', ['时间片越小，进程切换开销一定越小', '时间片很大时，可能退化为先来先服务', '只适用于非抢占式调度', '总能使平均周转时间最短'], 'B', '时间片足够大时，进程可能在一个时间片内运行结束，RR 的行为接近 FCFS。时间片过小反而可能增加上下文切换开销。', 3),
    ('q_tcp', 'tcp', 'single', 'TCP 如何识别可靠传输的数据？', 'TCP 报文段中，序号字段通常表示什么？', ['本报文段的编号', '本报文段数据部分第一个字节的序号', '下一个希望收到的字节序号', '已发送报文段的总数'], 'B', 'TCP 面向字节流，序号字段表示本报文段数据部分第一个字节的序号。确认号表示期望收到的下一个字节序号。', 3),
    ('q_tcp2', 'tcp', 'boolean', '确认号与累计确认', 'TCP 采用累计确认。若接收方发送 ACK=100，则表示序号小于 100 的字节均已按序收到。', ['正确', '错误'], '正确', '确认号为 100，表示接收方期待下一个字节的序号为 100，即此前的字节已经按序收到。', 3),
    ('q_sort', 'sort', 'multiple', '哪些排序算法是稳定的？', '在通常实现下，以下哪些排序算法是稳定的？', ['直接插入排序', '归并排序', '堆排序', '快速排序'], 'A,B', '直接插入排序和归并排序通常是稳定的；堆排序与快速排序通常不稳定。多选题按完全匹配计分。', 4),
    ('q_tree', 'tree', 'calculation', '由遍历序列还原二叉树', '某二叉树的先序遍历为 **A B D E C**，中序遍历为 **D B E A C**。\n\n请写出它的后序遍历序列，并简述划分左右子树的过程。', [], 'D E B C A', '先序首元素 A 为根。中序中 A 左侧为 D B E，右侧为 C。左子树根为 B，其左右孩子分别为 D、E。后序为 D E B C A。', 10),
    ('q_subnet', 'subnet', 'calculation', '一个子网有多少可用地址？', 'IPv4 网络 **192.168.10.0/26** 采用通常的子网主机地址分配规则。\n\n求子网掩码、地址总数和可分配给主机的地址数量。', [], '255.255.255.192；64 个地址；62 个可用主机地址。', '前缀为 26 位，主机位为 6 位。地址总数 $2^6=64$；扣除网络地址与广播地址后，可用主机地址为 62。掩码为 255.255.255.192。', 10),
    ('q_deadlock', 'deadlock', 'boolean', '安全状态与死锁', '系统处于不安全状态，就意味着系统已经发生死锁。', ['正确', '错误'], '错误', '不安全状态表示不能保证存在安全序列，可能导致死锁，但不意味着当前已经死锁。死锁状态一定是不安全状态。', 3),
    ('q_pipeline', 'pipeline', 'calculation', '理想流水线的执行时间', '一条理想指令流水线有 **5 级**，每级执行时间均为 **2 ns**。忽略流水线寄存器开销，连续执行 **10 条**独立指令需要多少时间？', [], '28 ns', '理想流水线总时间为 $(k+n-1)\\Delta t=(5+10-1)\\times2=28$ ns。', 10),
    ('q_memory', 'memory', 'calculation', '存储芯片扩展', '使用 **8K × 8 位** 的存储芯片组成 **32K × 16 位** 的存储器，需要多少片芯片？', [], '8 片', '字扩展为 $32K/8K=4$ 组，位扩展为 $16/8=2$ 片，总数为 $4\\times2=8$ 片。', 8),
    ('q_graph', 'graph', 'single', 'Dijkstra 算法的适用条件', '经典 Dijkstra 最短路径算法适用于以下哪种情况？', ['所有边权均非负', '图中允许任意负权边', '图中必须存在负权环', '只能用于无权图'], 'A', '经典 Dijkstra 算法依赖贪心地确定最短距离，要求边权非负。', 3),
    ('q_http', 'http', 'single', 'DNS 的作用', 'DNS 最主要的作用是？', ['加密 HTTP 内容', '将域名解析为相关资源记录', '分配 TCP 端口', '保证 IP 数据报可靠到达'], 'B', 'DNS 是域名系统，可查询 A、AAAA、MX 等资源记录。', 3),
    ('q_sort2', 'sort', 'single', '归并排序的时间复杂度', '对 n 个元素进行二路归并排序，其最坏时间复杂度为？', ['$O(n)$', '$O(n\\log n)$', '$O(n^2)$', '$O(\\log n)$'], 'B', '归并排序有约 $\\log_2 n$ 层，每层合并总工作量为 $O(n)$，总计 $O(n\\log n)$。', 3),
    ('q_page2', 'page', 'single', '页内偏移由什么决定？', '分页系统中，虚拟地址的页内偏移位数由什么决定？', ['虚拟页数量', '物理内存总容量', '页面大小', '页表项数量'], 'C', '页面大小为 $2^k$ 字节且按字节编址时，页内偏移为 k 位。', 3),
    ('q_tree2', 'tree', 'boolean', '完全二叉树与满二叉树', '每一棵满二叉树都是完全二叉树。', ['正确', '错误'], '正确', '按国内数据结构教材常见定义，满二叉树的各层节点均满，因此满足完全二叉树的排列要求。', 3),
]


def seed(db):
    db.executemany('INSERT OR IGNORE INTO knowledge VALUES (?,?,?,?)', KNOWLEDGE)
    for id_, kp, typ, title, body, options, answer, explanation, minutes in QUESTIONS:
        db.execute('''INSERT INTO questions(id,knowledge_id,type,title,body,options,answer,explanation,
            minutes,verified,source,is_demo,created_at) VALUES (?,?,?,?,?,?,?,?,?,1,?,1,?)''',
            (id_, kp, typ, title, body, dump(options), answer, explanation, minutes, '拾知原创示例 · 非真题', now()))
    history = [
        ('q_cache', -7, 'incorrect'), ('q_cache', -4, 'correct'),
        ('q_page', -6, 'incorrect'), ('q_page', -3, 'partial'),
        ('q_schedule', -8, 'incorrect'), ('q_schedule', -7, 'correct'),
        ('q_schedule', -4, 'correct'),
        ('q_tree', -6, 'correct'), ('q_tree', -5, 'correct'),
        ('q_sort', -5, 'correct'), ('q_sort', -4, 'correct'),
        ('q_deadlock', -3, 'incorrect'),
        ('q_memory', -4, 'correct'), ('q_memory', -3, 'correct'),
        ('q_pipeline', -2, 'correct'), ('q_graph', -1, 'correct'),
    ]
    for i, (qid, offset, grade) in enumerate(history):
        timestamp = (today() + timedelta(days=offset)).isoformat() + 'T10:00:00+08:00'
        db.execute('''INSERT INTO attempts(id,question_id,answer,grade,status,created_at,confirmed_at,is_demo,version)
            VALUES (?,?,?,?,?,?,?,?,1)''',
            (f'demo_attempt_{i}', qid, '示例作答记录', grade, 'confirmed', timestamp, timestamp, 1))
