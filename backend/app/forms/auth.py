from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo

# 直接使用简单的字符串作为标签，由模板中的翻译函数处理
class LoginForm(FlaskForm):
    """登录表单"""
    username = StringField('common.user.username', validators=[DataRequired(), Length(min=2, max=20)])
    password = PasswordField('common.user.password', validators=[DataRequired()])
    remember = BooleanField('common.user.remember')
    submit = SubmitField('common.button.login')

class RegisterForm(FlaskForm):
    """注册表单"""
    username = StringField('common.user.username', validators=[DataRequired(), Length(min=2, max=20)])
    password = PasswordField('common.user.password', validators=[DataRequired()])
    confirm_password = PasswordField('common.user.confirm_password', 
                                    validators=[DataRequired(), EqualTo('password', message='Passwords must match')])
    submit = SubmitField('common.button.register')
