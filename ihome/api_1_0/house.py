# coding=utf-8
# 导入蓝图对象
from . import api
# 导入redis实例
from ihome import redis_store, constants,db
# 导入flask内置对象
from flask import current_app, jsonify, g, request
# 导入模型类
from ihome.models import Area, House, Facility, HouseImage
# 导入自定义状态码
from ihome.utils.response_code import RET
# 导入登陆验证装饰器
from ihome.utils.commons import login_required
# 导入七牛云
from ihome.utils.image_storage import storage

# 导入json模块
import json


@api.route("/areas", methods=["GET"])
def get_areas_info():
    """
    获取城区信息:
    缓存----磁盘----缓存
    1/尝试从redis中获取城区信息
    2/判断查询结果是否有数据,如果有数据
    3/留下访问redis的中城区信息的记录,在日志中
    4/需要查询mysql数据库
    5/判断查询结果
    6/定义容器,存储查询结果
    7/遍历查询结果,添加到列表中
    8/对查询结果进行序列化,转成json
    9/存入redis缓存中
    10/返回结果
    :return:
    """
    # 尝试从redis中获取程序信息
    try:
        areas = redis_store.get("area_info")
    except Exception as e:
        current_app.logger.error(e)
        # 发生异常，把查询结果设置为None
        areas = None
    # 判断查询结果是否存在
    if areas:
        return '{"errno":0,"errmsg":"OK","data":%s}' % areas

    # 查询数据库
    try:
        areas = Area.query.all()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="查询城区信息异常")
    # 判断查询结果
    if not areas:
        return jsonify(errno=RET.NODATA, errmsg="无城区信息")
    # 定义容器
    areas_list = []
    for area in areas:
        # 需要调用模型类中的to_dict方法,把具体的查询对象转成键值形式的数据
        areas_list.append(area.to_dict())
    # 把城区信息转成json
    area_info = json.dumps((areas_list))
    # 存入redis
    try:
        redis_store.setex("area_info", constants.AREA_INFO_REDIS_EXPIRES, area_info)
    except Exception as e:
        current_app.logger.error(e)
    # 返回结果，城区信息已经是json字符串，不需要jsonify
    resp = '{"errno":0, "errmsg":"OK", "data":%s}' % area_info
    return resp

@api.route("/houses", methods=["POST"])
@login_required
def save_house_info():
    """
    发布新房源
    1/确认用户身份id
    2/获取参数,get_json()
    3/判断数据的存在
    4/获取详细的参数信息,指房屋的基本信息,不含配套设施title,price/area_id/address/unit/acreage/cacacity/beds/deposit/min_days/max_days/
    5/检查参数的完整性
    6/对价格参数进行转换,由元转成分
    7/构造模型类对象,准备存储数据
    8/判断配套设施的存在
    9/需要对配套设施进行过滤查询,后端只会保存数据库中已经定义的配套设施信息
    facilites = Facility.query.filter(Facility.id.in_(facility)).all()
    house.facilities = facilities
    10/保存数据到数据库中
    11/返回结果,house.id,让后面上传房屋图片和房屋进行关联
    :return:
    """
    # 获取user_id
    user_id = g.user_id
    # 获取post参数
    house_data = request.get_json()
    # 检验参数的存在
    if not house_data:
        return jsonify(errno=RET.PARAMERR, errmsg="参数错误")
    # 获取详细参数信息
    title = house_data.get("title") # 房屋标题
    area_id = house_data.get("area_id") # 房屋城区
    address = house_data.get("address") # 详细地址
    price = house_data.get("price") # 房屋价格
    room_count = house_data.get("room_count") # 房屋数目
    acreage = house_data.get("acreage") # 房屋面积
    unit = house_data.get("unit") # 房屋户型
    capacity = house_data.get("capacity") # 适住人数
    beds = house_data.get("beds") # 卧床配置
    deposit =house_data.get("deposit") # 押金
    min_days = house_data.get("min_days") # 最小入住天数
    max_days = house_data.get("max_days") # 最大入住天数
    # 检验参数完整性
    if not all([title,area_id,address,price,room_count,acreage,unit,capacity,beds,deposit,min_days,max_days]):
        return jsonify(errno=RET.PARAMERR, errmsg="参数错误")
    # 对价格参数进行转换
    try:
        price = int(float(price)*100)
        deposit = int(float(deposit)*100)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DATAERR, errmsg="价格数据错误")
    # 构造模型类对象
    house = House()
    house.user_id = user_id
    house.area_id = area_id
    house.title = title
    house.address = address
    house.price = price
    house.room_count = room_count
    house.acreage = acreage
    house.unit = unit
    house.capacity = capacity
    house.beds = beds
    house.deposit = deposit
    house.min_days = min_days
    house.max_days = max_days

    # 获取房屋配套设施参数信息
    facility = house_data.get("facility")
    # 判断配套设施的存在
    if facility:
        # 查询数据库，对房屋配套设施进行过滤查询，确保配套设施的编号在数据库中存在
        try:
            facilities = Facility.quert.filter(Facility.id.in_(facility)).all()
            # 保存房屋配套设施信息，配套设施的数据存在第三张表，关系引用在数据库中没有具体字段
            house.facilities = facilities
        except Exception as e:
            current_app.logger.error(e)
            return jsonify(errno=RET.DBERR, errmsg="查询配套设施异常")
    # 保存房屋数据到mysql数据库
    try:
        db.session.add(house)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR, errmsg="保存房屋数据失败")
    # 返回结果，house.id是用来后面实现上传房屋图片做准备（前段获取数据）
    return jsonify(errno=RET.OK, errmsg="OK", data={"house_id":house.id})