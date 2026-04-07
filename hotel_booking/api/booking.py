# # Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# # For license information, please see license.txt

# """
# Booking creation API - creates guest, checks availability, allocates rooms.
# """

# from datetime import datetime
# import json
# import frappe
# from frappe import _

# from hotel_booking.api.availability import check_room_availability
    
# # price logic with category priority: 1. Seasonal Price (Category wise) -> 2. Pricing Table -> 3. Base Price
# def _get_seasonal_price(room_type: str, check_in: str, check_out: str, category: str = None) -> float:
        
#     """
#     Priority: 1. Seasonal Price (Category wise) -> 2. Pricing Table -> 3. Base Price
#     """
#     # 1. Seasonal Price check karein Category ke saath
#     seasonal = frappe.db.sql(
#         """
#         SELECT price FROM `tabSeasonal Price`
#         WHERE room_type = %(room_type)s 
#         AND category = %(category)s
#         AND from_date <= %(check_out)s 
#         AND to_date >= %(check_in)s
#         ORDER BY from_date DESC LIMIT 1
#         """,
#         {"room_type": room_type, "category": category, "check_in": check_in, "check_out": check_out},
#         as_dict=True,
#     )

#     if seasonal and float(seasonal[0].price or 0) > 0:
#         return float(seasonal[0].price)

#     # 2. Agar seasonal nahi mila, toh 'Pricing' table check karein (Jo humne Client Script se bhari thi)
#     rt = frappe.get_cached_doc("Room Type", room_type)
#     if hasattr(rt, "pricing") and rt.pricing:
#         for row in rt.pricing:
#             if row.category == category and float(row.price or 0) > 0:
#                 return float(row.price)

#     # 3. Final Fallback: Base Price (Jo pehle se tha)
#     return float(rt.base_price or 0)



# def _allocate_rooms(room_type: str, check_in: str, check_out: str, count: int, category: str = None) -> list:
    
   
#     """
#     Allocate available rooms for the date range.
#     Uses SQL with FOR UPDATE for concurrent booking safety.
#     """
#     # Get rooms of this type that are Available and NOT in overlapping bookings
#     # Use subquery to exclude booked rooms
#     rooms = frappe.db.sql(
#         """
#         SELECT r.name
#         FROM `tabRoom` r
#         WHERE r.room_type = %(room_type)s
#         AND r.custom_category = %(category)s
#         AND r.status = 'Available'
#         AND r.name NOT IN (
#             SELECT DISTINCT br.room
#             FROM `tabBooking Room` br
#             INNER JOIN `tabBookings` b ON b.name = br.parent
#             WHERE br.room_type = %(room_type)s
#             AND b.status != 'Cancelled'
#             AND b.docstatus = 0
#             AND %(check_in)s < b.check_out
#             AND %(check_out)s > b.check_in
#         )
#         LIMIT %(count)s
#         """,
#         {"room_type": room_type,"category": category, "check_in": check_in, "check_out": check_out, "count": count},
#         as_dict=True,
#     )

#     return [r.name for r in rooms]    


# @frappe.whitelist(allow_guest=True)
# def create_booking(
#     guest_name: str = "",
#     phone: str = "",
#     email: str = "",
#     room_type: str = "",
#     check_in: str = "",
#     check_out: str = "",
#     rooms_required: int = 1,
#     adults: int = 1,
#     children: int = 0,
#     **kwargs,
# ) -> dict:
#     """
#     Create a booking: create/fetch guest, check availability, allocate rooms, create booking.

#     Args:
#         guest_name: Guest name
#         phone: Phone number
#         email: Email address
#         room_type: Room Type name
#         check_in: Check-in date (YYYY-MM-DD)
#         check_out: Check-out date (YYYY-MM-DD)
#         rooms_required: Number of rooms needed

#     Returns:
#         dict with booking_id
#     """
#     # Backward/compat payload normalization (keep function name unchanged)
#     payload = dict(kwargs or {})

#     if not payload and getattr(frappe, "request", None):
#         try:
#             payload = frappe.parse_json(frappe.request.get_data(as_text=True) or "{}") or {}
#             frappe.throw(f"Payload Received: {payload}")
#         except Exception:
#             payload = {}

#     first_name = (payload.get("first_name") or payload.get("firstName") or "").strip()
#     last_name = (payload.get("last_name") or payload.get("lastName") or "").strip()

#     if not guest_name:
#         guest_name = (payload.get("guest_name") or payload.get("guestName") or f"{first_name} {last_name}").strip()

#     phone = phone or payload.get("phone") or payload.get("mobile") or ""
#     email = email or payload.get("email") or ""
#     room_type = room_type or payload.get("room_type") or payload.get("roomType") or payload.get("room") or ""
#     check_in = check_in or payload.get("check_in") or payload.get("checkIn") or payload.get("checkin") or ""
#     check_out = check_out or payload.get("check_out") or payload.get("checkOut") or payload.get("checkout") or ""
#     category = payload.get("category") or payload.get("categoryName") or ""
    
   
    
#     rooms_required = rooms_required or payload.get("rooms_required") or payload.get("rooms") or 1
#     adults = adults or payload.get("adults") or 1
#     children = children or payload.get("children") or 0

#     # Validate inputs
#     if not all([guest_name, room_type, check_in, check_out]):
#         frappe.throw(_("Guest name, room type, check-in and check-out are required"))

#     rooms_required = int(rooms_required or 1)
#     if rooms_required < 1:
#         frappe.throw(_("At least 1 room is required"))

#     adults = int(adults or 1)
#     children = int(children or 0)
#     frappe.log_error(f"adults:{adults}, children:{children}")
#     if adults < 1:
#         frappe.throw(_("At least 1 adult is required"))

#     # Parse dates
#     try:
#         check_in_dt = datetime.strptime(str(check_in).strip(), "%Y-%m-%d").date()
#         check_out_dt = datetime.strptime(str(check_out).strip(), "%Y-%m-%d").date()
#     except (ValueError, TypeError):
#         frappe.throw(_("Invalid date format. Use YYYY-MM-DD"))

#     if check_in_dt >= check_out_dt:
#         frappe.throw(_("Check-out date must be after check-in date"))

#     if not frappe.db.exists("Room Type", room_type):
#         frappe.throw(_("Room Type {0} does not exist").format(room_type))

#     # Validate guest capacity start
    
#     # --- New Logic for Child Table (Room Tariff) ---
#     parent_doc = frappe.get_doc("Room Type", room_type)
    
#     # max_limit = 0

#     # # Aapki child table ka naam 'room_tariff' ya 'pricing' ho sakta hai, 
#     # # use check karke yahan likhein (mostly 'room_tariff' hota hai)
#     # # for row in parent_doc.get("Room Tariff"): 
#     # for row in (parent_doc.get("room_tariff") or parent_doc.get("Room Tariff") or []):
#     #     if row.category == category:
#     #         max_limit = row.max_guest #
#     #         break

#     # # Agar Room Tariff mein capacity nahi mili toh fallback error
#     # if not max_limit:
#     #     frappe.throw(_("Capacity not defined for {0} in Room Tariff.").format(category))

#     # total_guests = int(adults) + int(children)
#     # total_capacity = int(max_limit) * int(rooms_required)

#     # if total_guests > total_capacity:
#     #     frappe.throw(
#     #         _("Guest count ({0}) exceeds maximum capacity for {1}. Max allowed per room: {2}")
#     #         .format(total_guests, category, max_limit)
#     #     )
#     # --- End of New Logic ---
    
    
#     # 1. Frontend se aane waale JSON ko list mein badlein
#     category_raw = payload.get("category")
#     selected_categories = []

#     if isinstance(category_raw, str) and category_raw.startswith("["):
#         try:
#             parsed_data = json.loads(category_raw)
#             # Sirf category ke naam nikaalein, jaise ["Cottages", "Deluxe Room"]
#             selected_categories = [item.get("category") for item in parsed_data if item.get("category")]
#         except Exception:
#             selected_categories = [category_raw]
#     else:
#         selected_categories = [category_raw] if category_raw else []

#     # 2. Capacity check karne ka naya tarika (Multiple categories ke liye)
#     max_limit = 0
#     found_any = False
    
#     # Dono possible field names check karein
#     tariff_table = parent_doc.get("room_tariff") or parent_doc.get("Room Tariff") or []

#     for row in tariff_table:
#         if row.category in selected_categories:
#             # Sabhi selected categories ki capacity ko plus (+) karein
#             max_limit += (int(row.max_guest) if row.max_guest else 0)
#             found_any = True

#     # 3. Agar koi category match nahi hui
#     if not found_any:
#         frappe.throw(f"Capacity not defined for {selected_categories} in Room Tariff table.")

#     # 4. Total calculation
#     total_guests = int(payload.get("adults") or 0) + int(payload.get("children") or 0)
#     # Total capacity = (Selected rooms ki total capacity) * (Kitne rooms mangey hain)
#     total_allowed = max_limit * int(payload.get("rooms_required") or 1)

#     if total_guests > total_allowed:
#         frappe.throw(f"Guest count ({total_guests}) exceeds total capacity ({total_allowed}).")    
        
        
#     # Check availability (re-validate at creation time)
#     available = check_room_availability(room_type, check_in, check_out, category)
#     if available < rooms_required:
#         frappe.throw(
#             _("Only {0} room(s) available for selected dates. Required: {1}").format(
#                 available, rooms_required
#             )
#         )

#     # Create or fetch guest (match by phone or email for simplicity)
#     guest = None
#     if phone:
#         guest = frappe.db.get_value("Guest", {"phone": phone}, "name")
#     if not guest and email:
#         guest = frappe.db.get_value("Guest", {"email": email}, "name")

#     if not guest:
#         guest_doc = frappe.get_doc(
#             {
#                 "doctype": "Guest",
#                 "guest_name": guest_name,
#                 "phone": phone or "",
#                 "email": email or "",
#             }
#         )
#         guest_doc.insert(ignore_permissions=True)
#         guest = guest_doc.name
#     else:
#         # Update guest details if changed
#         guest_doc = frappe.get_doc("Guest", guest)
#         guest_doc.guest_name = guest_name
#         guest_doc.phone = phone or guest_doc.phone
#         guest_doc.email = email or guest_doc.email
#         guest_doc.save(ignore_permissions=True)

#     # Get price and calculate
#     price_per_night = _get_seasonal_price(room_type, check_in, check_out, category)
#     nights = (check_out_dt - check_in_dt).days
#     frappe.log_error(f"price_per_night:{price_per_night}, nights:{nights}")

#     # Allocate rooms (within transaction for concurrency)
#     allocated = _allocate_rooms(room_type, check_in, check_out, rooms_required, category)
#     if len(allocated) < rooms_required:
#         frappe.throw(_("Rooms could not be allocated. Please try again."))

#     # Create booking
#     rooms_data = []
#     for room_name in allocated:
#         room_doc = frappe.get_cached_doc("Room", room_name)
#         amount = price_per_night * nights
#         rooms_data.append(
#             {
#                 "room": room_name,
#                 "room_type": room_type,
#                 "price_per_night": price_per_night,
#                 "nights": nights,
#                 "amount": amount,
#                 "adults": adults,
#                 "children": children,
#             }
#         )

#     total_amount = sum(r["amount"] for r in rooms_data)

#     booking = frappe.get_doc(
#         {
#             # "doctype": "Booking",
#             "doctype": "Bookings",
#             "guest": guest,
#             "check_in": check_in,
#             "check_out": check_out,
#             "rooms_required": rooms_required,
#             "adults": adults,
#             "children": children,
#             "total_amount": total_amount,
#             "status": "Pending Payment",
#             "payment_status": "Unpaid",
#             "rooms": rooms_data,
#         }
#     )
#     booking.insert(ignore_permissions=True)
#     frappe.db.commit()

#     # return {"booking_id": booking.name, "total_amount": total_amount, "rooms_required": rooms_required, "adults": adults, "children": children}
#     return {
#         "booking_id": str(booking.name),
#         "total_amount": float(total_amount),
#         "rooms_required": int(rooms_required),
#         "adults": int(adults),
#         "children": int(children),
#     }

# # @frappe.whitelist(allow_guest=True)
# # def get_room_price(room_type: str, check_in: str, check_out: str, category: str = None) -> dict:
# #     price = _get_seasonal_price(room_type, check_in, check_out, category)
# #     return {"price": float(price)}

# @frappe.whitelist(allow_guest=True)
# def get_room_price(room_type, check_in, check_out, category):
#     from datetime import datetime, timedelta
    
#     # 1. Regular Price fetch karein (Sirf category filter use karke)
#     # Kyunki aapke Room Tariff mein 'room_type' field nahi hai
#     regular_price = frappe.db.get_value("Room Tariff", {"category": category}, "price")

#     d1 = datetime.strptime(check_in, "%Y-%m-%d").date()
#     d2 = datetime.strptime(check_out, "%Y-%m-%d").date()
#     total_days = (d2 - d1).days
#     total_price = 0

#     if total_days <= 0: total_days = 1 

#     # 2. Har din ke liye Seasonal Price check karein
#     for i in range(total_days):
#         current_date = d1 + timedelta(days=i)
        
#         # Seasonal Price mein 'room_type' field hai, isliye yahan use karenge
#         seasonal_day = frappe.db.sql("""
#             SELECT price FROM `tabSeasonal Price`
#             WHERE room_type = %s AND category = %s
#             AND %s BETWEEN from_date AND to_date
#             LIMIT 1
#         """, (room_type, category, current_date), as_dict=True)

#         if seasonal_day:
#             total_price += float(seasonal_day[0].price)
#         else:
#             total_price += float(regular_price or 0)

#     avg_price = total_price / total_days
    
#     return {
#         "price": avg_price,
#         "is_seasonal": total_price < (float(regular_price or 0) * total_days)
#     }

# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


#######################################corect code for booking API with category based pricing and capacity check#######################################
# import json
# import frappe
# from frappe import _
# from frappe.utils import flt
# from datetime import datetime

# @frappe.whitelist(allow_guest=True)
# def create_booking(**kwargs):
#     try:
#         # 1. Payload setup
#         payload = dict(kwargs or {})
#         if not payload and getattr(frappe, "request", None):
#             payload = frappe.parse_json(frappe.request.get_data(as_text=True) or "{}") or {}

#         # 2. Extract Data
#         guest_name = (payload.get("guest_name") or "New Guest").strip()
#         room_type = payload.get("room_type") or ""
#         check_in = payload.get("check_in") or ""
#         check_out = payload.get("check_out") or ""
#         rooms_req = int(payload.get("rooms_required") or 1)

#         # 3. Guest Management (Mandatory for Link Field)
#         # Check if guest exists
#         guest_id = frappe.db.get_value("Guest", {"guest_name": guest_name}, "name")
        
#         if not guest_id:
#             new_guest = frappe.get_doc({
#                 "doctype": "Guest",
#                 "guest_name": guest_name,
#                 "email": payload.get("email") or "",
#                 "phone": payload.get("phone") or ""
#             })
#             new_guest.insert(ignore_permissions=True)
#             guest_id = new_guest.name

#         # 4. Simple Price Calculation
#         base_price = frappe.db.get_value("Room Type", room_type, "base_price") or 5000
        
#         d1 = datetime.strptime(check_in, "%Y-%m-%d")
#         d2 = datetime.strptime(check_out, "%Y-%m-%d")
#         nights = (d2 - d1).days
#         if nights <= 0: nights = 1
        
#         total_amt = flt(base_price) * nights * rooms_req

#         # 5. Insert Booking (Field names from image_b6e0c8.png)
#         booking_doc = frappe.get_doc({
#             "doctype": "Bookings",
#             "guest": guest_id,           # Mandatory Link Field
#             "check_in": check_in,        # Date field
#             "check_out": check_out,      # Date field
#             "total_amount": total_amt,   # Currency field
#             "status": "Pending Payment", # Select field
#             "payment_status": "Unpaid"    # Select field
#         })
        
#         booking_doc.insert(ignore_permissions=True)
#         frappe.db.commit()

#         return {
#             "booking_id": str(booking_doc.name),
#             "total_amount": float(total_amt)
#         }

#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Booking API Error")
#         frappe.throw(_("Server Error: {0}").format(str(e)))
        
# @frappe.whitelist(allow_guest=True)
# def get_room_price(room_type, check_in, check_out, category):
#     from datetime import datetime, timedelta
    
#     # 1. Regular Price fetch karein (Sirf category filter use karke)
#     # Kyunki aapke Room Tariff mein 'room_type' field nahi hai
#     regular_price = frappe.db.get_value("Room Tariff", {"category": category}, "price")

#     d1 = datetime.strptime(check_in, "%Y-%m-%d").date()
#     d2 = datetime.strptime(check_out, "%Y-%m-%d").date()
#     total_days = (d2 - d1).days
#     total_price = 0

#     if total_days <= 0: total_days = 1 

#     # 2. Har din ke liye Seasonal Price check karein
#     for i in range(total_days):
#         current_date = d1 + timedelta(days=i)
        
#         # Seasonal Price mein 'room_type' field hai, isliye yahan use karenge
#         seasonal_day = frappe.db.sql("""
#             SELECT price FROM `tabSeasonal Price`
#             WHERE room_type = %s AND category = %s
#             AND %s BETWEEN from_date AND to_date
#             LIMIT 1
#         """, (room_type, category, current_date), as_dict=True)

#         if seasonal_day:
#             total_price += float(seasonal_day[0].price)
#         else:
#             total_price += float(regular_price or 0)

#     avg_price = total_price / total_days
    
#     return {
#         "price": avg_price,
#         "is_seasonal": total_price < (float(regular_price or 0) * total_days)
#     }
    
    
import json
import frappe
from frappe import _
from frappe.utils import flt
from datetime import datetime

@frappe.whitelist(allow_guest=True)
def create_booking(**kwargs):
    try:
        payload = dict(kwargs or {})
        if not payload and getattr(frappe, "request", None):
            payload = frappe.parse_json(frappe.request.get_data(as_text=True) or "{}") or {}

        # 1. Category Data Parsing
        category_data = payload.get("category") or []
        if isinstance(category_data, str):
            try:
                category_data = json.loads(category_data)
            except:
                category_data = [{"category": category_data, "rooms": int(payload.get("rooms_required") or 1)}]

        # 2. Extract Basic Info
        guest_name = (payload.get("guest_name") or "New Guest").strip()
        room_type = payload.get("room_type") or ""
        check_in = payload.get("check_in") or ""
        check_out = payload.get("check_out") or ""

        # 3. Create/Get Guest
        guest_id = frappe.db.get_value("Guest", {"guest_name": guest_name}, "name")
        if not guest_id:
            g = frappe.get_doc({"doctype": "Guest", "guest_name": guest_name, "email": payload.get("email")})
            g.insert(ignore_permissions=True)
            guest_id = g.name

        # 4. Loop through categories and Fill Child Table
        rooms_child_rows = []
        total_amt = 0
        
        d1 = datetime.strptime(check_in, "%Y-%m-%d").date()
        d2 = datetime.strptime(check_out, "%Y-%m-%d").date()
        nights = (d2 - d1).days or 1

        for item in category_data:
            cat_name = item.get("category")
            num_rooms = int(item.get("rooms") or 1)
            
            # Find available rooms
            available = frappe.get_all("Room", 
                filters={"room_type": room_type, "custom_category": cat_name, "status": "Available"},
                limit=num_rooms
            )

            if len(available) < num_rooms:
                frappe.throw(_("Not enough Available rooms for {0}").format(cat_name))

            price = flt(item.get("price") or frappe.db.get_value("Room Tariff", {"category": cat_name}, "price") or 0)

            for i in range(num_rooms):
                row_amount = price * nights
                rooms_child_rows.append({
                    "room": available[i].name,
                    "room_type": room_type,
                    "price_per_night": price,
                    "nights": nights,
                    "amount": row_amount,
                    "adults": int(item.get("adults") or 1),
                    "children": int(item.get("children") or 0),
                    "category": cat_name
                })
                total_amt += row_amount

        # 5. Save the Booking (CORRECTED STATUS CASE)
        booking_doc = frappe.get_doc({
            "doctype": "Bookings",
            "guest": guest_id,
            "check_in": check_in,
            "check_out": check_out,
            "total_amount": total_amt,
            "status": "Confirmed",        # Capital 'C'
            "payment_status": "Unpaid",    # Capital 'U' (Check if your field uses 'Unpaid' or 'Pending')
            "razorpay_order_id": payload.get("razorpay_order_id") or "",
            "rooms": rooms_child_rows 
        })
        
        booking_doc.insert(ignore_permissions=True)
        
        # Room status update
        for r in rooms_child_rows:
            frappe.db.set_value("Room", r["room"], "status", "Booked")

        frappe.db.commit()

        return {"booking_id": booking_doc.name, "total_amount": total_amt}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Final Booking Error")
        frappe.throw(str(e))

@frappe.whitelist(allow_guest=True)
def get_room_price(room_type, check_in, check_out, category):
    from datetime import datetime, timedelta
    
    # 1. Regular Price fetch karein (Sirf category filter use karke)
    # Kyunki aapke Room Tariff mein 'room_type' field nahi hai
    regular_price = frappe.db.get_value("Room Tariff", {"category": category}, "price")

    d1 = datetime.strptime(check_in, "%Y-%m-%d").date()
    d2 = datetime.strptime(check_out, "%Y-%m-%d").date()
    total_days = (d2 - d1).days
    total_price = 0

    if total_days <= 0: total_days = 1 

    # 2. Har din ke liye Seasonal Price check karein
    for i in range(total_days):
        current_date = d1 + timedelta(days=i)
        
        # Seasonal Price mein 'room_type' field hai, isliye yahan use karenge
        seasonal_day = frappe.db.sql("""
            SELECT price FROM `tabSeasonal Price`
            WHERE room_type = %s AND category = %s
            AND %s BETWEEN from_date AND to_date
            LIMIT 1
        """, (room_type, category, current_date), as_dict=True)

        if seasonal_day:
            total_price += float(seasonal_day[0].price)
        else:
            total_price += float(regular_price or 0)

    avg_price = total_price / total_days
    
    return {
        "price": avg_price,
        "is_seasonal": total_price < (float(regular_price or 0) * total_days)
    }