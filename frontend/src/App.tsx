import { useState, useRef, useCallback } from 'react'

// API base URL
const API_URL = '/api'

type View = 'login' | 'verify' | 'dashboard'

interface Teacher {
    id: number
    first_name: string
}

function App() {
    const [view, setView] = useState<View>('login')
    const [phone, setPhone] = useState('')
    const [code, setCode] = useState('')
    const [loading, setLoading] = useState(false)
    const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null)
    const [teacher, setTeacher] = useState<Teacher | null>(null)
    const [hasQuiz, setHasQuiz] = useState(false)

    const fileInputRef = useRef<HTMLInputElement>(null)

    // Send verification code
    const handleSendCode = async (e: React.FormEvent) => {
        e.preventDefault()
        setLoading(true)
        setMessage(null)

        try {
            const res = await fetch(`${API_URL}/auth/send-code`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone })
            })
            const data = await res.json()

            if (data.success) {
                setMessage({ type: 'success', text: data.message })
                setView('verify')
            } else {
                setMessage({ type: 'error', text: data.message })
            }
        } catch (err) {
            setMessage({ type: 'error', text: 'خطأ في الاتصال بالخادم' })
        }

        setLoading(false)
    }

    // Verify code
    const handleVerify = async (e: React.FormEvent) => {
        e.preventDefault()
        setLoading(true)
        setMessage(null)

        try {
            const res = await fetch(`${API_URL}/auth/verify`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone, code })
            })
            const data = await res.json()

            if (data.success) {
                setTeacher({ id: data.teacher_id, first_name: data.first_name })
                setMessage({ type: 'success', text: data.message })
                setView('dashboard')
                // Load quiz status
                loadQuizStatus(data.teacher_id)
            } else {
                setMessage({ type: 'error', text: data.detail || data.message })
            }
        } catch (err) {
            setMessage({ type: 'error', text: 'خطأ في الاتصال بالخادم' })
        }

        setLoading(false)
    }

    // Load quiz status
    const loadQuizStatus = async (teacherId: number) => {
        try {
            const res = await fetch(`${API_URL}/quiz/current/${teacherId}`)
            const data = await res.json()
            setHasQuiz(data.has_quiz)
        } catch (err) {
            console.error('Error loading quiz status')
        }
    }

    // Upload quiz
    const handleUploadQuiz = async (file: File) => {
        if (!teacher) return

        setLoading(true)
        setMessage(null)

        try {
            const formData = new FormData()
            formData.append('file', file)

            const res = await fetch(`${API_URL}/quiz/upload?teacher_id=${teacher.id}`, {
                method: 'POST',
                body: formData
            })
            const data = await res.json()

            if (data.success) {
                setMessage({ type: 'success', text: 'تم رفع الاختبار بنجاح! ✅' })
                setHasQuiz(true)
            } else {
                setMessage({ type: 'error', text: data.detail || 'فشل رفع الاختبار' })
            }
        } catch (err) {
            setMessage({ type: 'error', text: 'خطأ في رفع الملف' })
        }

        setLoading(false)
    }

    // Handle file selection
    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (file) handleUploadQuiz(file)
    }

    // Drag and drop
    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault()
        const file = e.dataTransfer.files[0]
        if (file && file.type.startsWith('image/')) {
            handleUploadQuiz(file)
        }
    }, [teacher])

    // Logout
    const handleLogout = () => {
        setTeacher(null)
        setPhone('')
        setCode('')
        setView('login')
        setMessage(null)
        setHasQuiz(false)
    }

    return (
        <div className="app">
            {/* Logo */}
            <div className="logo">📚</div>
            <h1 className="title">المعلم</h1>
            <p className="subtitle">نظام التصحيح الذكي</p>

            {/* Message */}
            {message && (
                <div className={`message ${message.type}`}>
                    {message.text}
                </div>
            )}

            {/* Login View */}
            {view === 'login' && (
                <div className="card">
                    <h2 className="card-title">تسجيل الدخول</h2>
                    <form onSubmit={handleSendCode}>
                        <div className="form-group">
                            <label className="label">رقم الهاتف (مع رمز الدولة)</label>
                            <input
                                type="tel"
                                className="input"
                                placeholder="+964xxxxxxxxx"
                                value={phone}
                                onChange={(e) => setPhone(e.target.value)}
                                required
                            />
                        </div>
                        <button type="submit" className="btn" disabled={loading}>
                            {loading ? <>جاري الإرسال <span className="spinner"></span></> : 'إرسال رمز التحقق'}
                        </button>
                    </form>
                </div>
            )}

            {/* Verify View */}
            {view === 'verify' && (
                <div className="card">
                    <h2 className="card-title">أدخل رمز التحقق</h2>
                    <form onSubmit={handleVerify}>
                        <div className="form-group">
                            <label className="label">الرمز من تيليجرام</label>
                            <input
                                type="text"
                                className="input"
                                placeholder="12345"
                                value={code}
                                onChange={(e) => setCode(e.target.value)}
                                required
                                autoFocus
                            />
                        </div>
                        <button type="submit" className="btn" disabled={loading}>
                            {loading ? <>جاري التحقق <span className="spinner"></span></> : 'تأكيد'}
                        </button>
                    </form>
                    <button
                        className="btn btn-secondary"
                        style={{ marginTop: 10 }}
                        onClick={() => setView('login')}
                    >
                        رجوع
                    </button>
                </div>
            )}

            {/* Dashboard View */}
            {view === 'dashboard' && teacher && (
                <div className="dashboard">
                    <div className="dashboard-header">
                        <h2 className="welcome">مرحباً، {teacher.first_name} 👋</h2>
                        <button className="logout-btn" onClick={handleLogout}>
                            تسجيل الخروج
                        </button>
                    </div>

                    <div className="card">
                        <h3 className="card-title">رفع صورة الاختبار</h3>

                        <div
                            className={`upload-zone ${hasQuiz ? 'active' : ''}`}
                            onClick={() => fileInputRef.current?.click()}
                            onDragOver={(e) => e.preventDefault()}
                            onDrop={handleDrop}
                        >
                            <div className="upload-icon">{hasQuiz ? '✅' : '📷'}</div>
                            <p className="upload-text">
                                {hasQuiz
                                    ? 'تم تعيين الاختبار! اضغط لتغييره'
                                    : 'اضغط أو اسحب صورة السؤال هنا'}
                            </p>
                        </div>

                        <input
                            ref={fileInputRef}
                            type="file"
                            accept="image/*"
                            style={{ display: 'none' }}
                            onChange={handleFileChange}
                        />

                        {hasQuiz && (
                            <div className="quiz-status">
                                <span>✓</span>
                                <span>البوت جاهز لتصحيح إجابات الطلاب تلقائياً</span>
                            </div>
                        )}
                    </div>

                    <div className="stats-grid">
                        <div className="stat-card">
                            <div className="stat-value">{hasQuiz ? '✓' : '✗'}</div>
                            <div className="stat-label">حالة الاختبار</div>
                        </div>
                        <div className="stat-card">
                            <div className="stat-value">نشط</div>
                            <div className="stat-label">حالة البوت</div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}

export default App
