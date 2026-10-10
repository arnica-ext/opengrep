class User < ActiveRecord::Base
acts_as_authentic do |t|
    t.login_field=:login # for available options see documentation in: Authlogic::ActsAsAuthentic
  end # block optional
    attr_accessible :login
  attr_accessible :first_name
    attr_accessible :middle_name
    attr_accessible :surname
    attr_accessible :permanent_address
    attr_accessible :correspondence_address
    attr_accessible :email
    attr_accessible :contact_no
    attr_accessible :gender
    attr_accessible :password
    attr_accessible :password_confirmation
    attr_accessible :avatar
    has_attached_file :avatar, :styles => { :medium => "300x300>", :thumb => "100x100>" }
end

def create
    user = User.create(person_params)
end

# ruleid: model-attributes-attr-accessible
class User < ActiveRecord::Base
acts_as_authentic do |t|
    t.login_field=:login # for available options see documentation in: Authlogic::ActsAsAuthentic
  end # block optional
    has_attached_file :avatar, :styles => { :medium => "300x300>", :thumb => "100x100>" }
end

def create
    user = User.create(person_params)
end

class SomeErrorClass < RuntimeError

  def initialize()
  end

end

#ok: model-attributes-attr-accessible
SomeErrorClass.new()

#todook: model-attributes-attr-accessible
class TestObject < Struct.new(:name); end
TestObject.new("name")

# Additional test cases

# ruleid: model-attributes-attr-accessible
class UserWithPublicAttributes < ActiveRecord::Base
  attr_accessible :username, :email, :password, :bio
  has_attached_file :profile_picture, :styles => { :medium => "300x300>", :thumb => "100x100>" }
end

user = UserWithPublicAttributes.new(username: "john_doe", bio: "Software Developer")

# ok: model-attributes-attr-accessible
class SecureUser < ActiveRecord::Base
  attr_accessor :username, :email, :password
  has_attached_file :profile_picture, :styles => { :medium => "300x300>", :thumb => "100x100>" }

  def initialize(params)
    @username = params[:username]
    @password = params[:password]
    @profile_picture = params[:profile_picture]
  end
end

secure_user = SecureUser.new(username: "jane_doe", password: "securepass")

# ruleid: model-attributes-attr-accessible
class Profile < ActiveRecord::Base
  attr_accessible :nickname
  has_attached_file :cover_photo, :styles => { :large => "500x500>", :small => "200x200>" }
end

profile = Profile.new(nickname: "coolguy")

# ok: model-attributes-attr-accessible
class Admin < ActiveRecord::Base
  attr_accessor :identification
  has_attached_file :badge, :styles => { :large => "600x600>", :icon => "64x64>" }

  def assign_identification(id)
    self.identification = id
  end
end

admin = Admin.new
admin.assign_identification("admin-123")
